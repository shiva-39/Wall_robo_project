"""
Wall-Finishing Robot Control System - Enhanced Backend API
Robust, optimized, database-driven system for autonomous robot path planning.
"""


import sqlite3
import json
import logging
import time
from decimal import Decimal, getcontext
from typing import List, Optional, Dict, Any, Union, Callable
from fastapi import WebSocket
from datetime import datetime, timezone # <--- CORRECTION: Added timezone
from contextlib import asynccontextmanager
from fastapi import WebSocket


from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationInfo
import uvicorn
import asyncio
from concurrent.futures import ThreadPoolExecutor


from config import get_settings, Settings
import jwt
from jwt import PyJWTError


# --- CONFIGURATION & INITIALIZATION ---


settings = get_settings()
getcontext().prec = settings.decimal_precision


# Thread pool for SQLite I/O operations
executor = ThreadPoolExecutor(max_workers=settings.db_pool_size)


# Structured logging configuration
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('robot_api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)



# --- LIFESPAN MANAGEMENT ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    logger.info("Starting Wall-Finishing Robot Control System")
    # Initialize DB
    init_db()

    # Optional MQTT client (for real-time notifications)
    app.state.mqtt_client = None
    if getattr(settings, 'mqtt_enabled', False):
        try:
            import paho.mqtt.client as mqtt
            mqtt_client = mqtt.Client()
            # Use a short connect timeout; if broker unavailable we continue without MQ
            mqtt_client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
            mqtt_client.loop_start()
            app.state.mqtt_client = mqtt_client
            logger.info(f"[OK] MQTT client connected to {settings.mqtt_host}:{settings.mqtt_port}")
        except Exception as e:
            logger.warning(f"[WARN] MQTT client initialization failed: {e}")

    try:
        yield
    finally:
        logger.info("Shutting down gracefully...")
        # Shutdown ThreadPoolExecutor
        executor.shutdown(wait=True)

        # Stop MQTT loop if started
        mqtt_client = getattr(app.state, 'mqtt_client', None)
        if mqtt_client is not None:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
                logger.info("[OK] MQTT client disconnected")
            except Exception:
                logger.warning("[WARN] Error while disconnecting MQTT client")


            # cancel maintenance task if present
            maint = getattr(app.state, 'db_maintenance_task', None)
            if maint is not None:
                try:
                    maint.cancel()
                except Exception:
                    pass



app = FastAPI(
    title="Wall-Finishing Robot Control API",
    version="2.0.0",
    description="Advanced path planning system for autonomous wall-finishing robots",
    lifespan=lifespan
)


def _require_api_key(request: Request):
    """Dependency to require API key for sensitive endpoints.

    Accepts either `X-API-Key` header or `Authorization: Bearer <key>`.
    If `settings.api_key` is empty, no key is required (disabled).
    """
    if not getattr(settings, 'api_key', None):
        return True

    key = request.headers.get('X-API-Key')
    if not key:
        auth = request.headers.get('authorization', '')
        if auth.lower().startswith('bearer '):
            key = auth.split(None, 1)[1].strip()

    if not key or key != settings.api_key:
        raise HTTPException(status_code=401, detail='Unauthorized')

    return True


security = HTTPBearer(auto_error=False)


def _verify_jwt_token(token: str) -> bool:
    """Verify JWT token using settings.jwt_secret if configured."""
    secret = getattr(settings, 'jwt_secret', '')
    if not secret:
        return False
    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        return True
    except PyJWTError:
        return False


def require_auth(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Dependency to require either API key or valid JWT.

    Priority: API key via X-API-Key or Authorization: Bearer <key> matching settings.api_key.
    Otherwise, accept JWT if settings.jwt_secret is configured and token verifies.
    """
    # First try API key
    try:
        return _require_api_key(request)
    except HTTPException:
        # Try JWT
        pass

    # If a bearer token is present and jwt_secret configured, verify it
    if credentials and credentials.scheme.lower() == 'bearer':
        token = credentials.credentials
        if _verify_jwt_token(token):
            return True

    raise HTTPException(status_code=401, detail='Unauthorized')


def rate_limit_decorator(limit_spec: str):
    """Return a decorator that applies rate limiting when Redis limiter is configured.

    If no Redis limiter is configured, returns identity decorator.
    """
    limiter_obj = getattr(app.state, 'limiter', None)
    if limiter_obj is None:
        def _identity(fn):
            return fn
        return _identity
    return limiter_obj.limit(limit_spec)


# Optional Redis-backed rate limiter (uses slowapi). Enabled when `settings.redis_url` is set.
if getattr(settings, 'redis_url', ''):
    try:
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.errors import _rate_limit_exceeded_handler

        limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
        logger.info(f"[OK] Redis-backed rate limiter initialized (redis: {settings.redis_url})")
    except Exception as e:
        logger.warning(f"[WARN] Could not initialize Redis rate limiter: {e}")



# --- PYDANTIC MODELS ---


class Obstacle(BaseModel):
    """Rectangular obstacle definition."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    id: str = Field(..., description="Unique obstacle identifier")
    x: Union[float, str, Decimal] = Field(..., description="Bottom-left X coordinate (m)")
    y: Union[float, str, Decimal] = Field(..., description="Bottom-left Y coordinate (m)")
    width: Union[float, str, Decimal] = Field(..., description="Width (m)")
    height: Union[float, str, Decimal] = Field(..., description="Height (m)")
    
    @field_validator('x', 'y', 'width', 'height', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert input to Decimal."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    
    @field_validator('x', 'y', 'width', 'height')
    @classmethod
    def validate_positive(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Coordinates and dimensions must be non-negative")
        return v



class WallPlanRequest(BaseModel):
    """Path planning request schema."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    wall_width: Union[float, str, Decimal] = Field(..., description="Wall width (m)")
    wall_height: Union[float, str, Decimal] = Field(..., description="Wall height (m)")
    obstacles: List[Obstacle] = Field(default_factory=list, description="Obstacle list")
    tool_width: Union[float, str, Decimal] = Field(
        default=Decimal(str(settings.default_tool_width)),
        description="Robot tool/brush width (m)"
    )
    coverage_margin: Union[float, str, Decimal] = Field(
        default=Decimal(str(settings.default_coverage_margin)),
        description="Safety margin (m)"
    )
    
    @field_validator('wall_width', 'wall_height', 'tool_width', 'coverage_margin', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert input to Decimal."""
        if isinstance(v, Decimal):
            return v
        if v is None:
            return None
        return Decimal(str(v))
    
    @field_validator('wall_width', 'wall_height', 'tool_width')
    @classmethod
    def validate_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Dimensions must be positive")
        return v
    
    @field_validator('coverage_margin')
    @classmethod
    def validate_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Margin must be non-negative")
        return v


    @field_validator('obstacles')
    @classmethod
    def validate_obstacles_within_wall(cls, obstacles: List[Obstacle], info: ValidationInfo) -> List[Obstacle]:
        """Ensure all obstacles are within wall boundaries."""
        # Skip validation if wall dimensions aren't available yet
        if 'wall_width' not in info.data or 'wall_height' not in info.data:
            return obstacles
        
        # Get wall dimensions and ensure they're Decimals
        w = info.data['wall_width']
        h = info.data['wall_height']
        
        if not isinstance(w, Decimal):
            w = Decimal(str(w))
        if not isinstance(h, Decimal):
            h = Decimal(str(h))
        
        # Validate each obstacle
        for obs in obstacles:
            # Get obstacle properties - they're already Decimals from the Obstacle validator
            obs_x = obs.x
            obs_y = obs.y
            obs_width = obs.width
            obs_height = obs.height
            
            # Check boundaries
            if obs_x + obs_width > w:
                raise ValueError(f"Obstacle {obs.id} exceeds wall width (x: {obs_x} + width: {obs_width} = {obs_x + obs_width} > wall: {w})")
            if obs_y + obs_height > h:
                raise ValueError(f"Obstacle {obs.id} exceeds wall height (y: {obs_y} + height: {obs_height} = {obs_y + obs_height} > wall: {h})")
        
        return obstacles




class PathMetrics(BaseModel):
    """Path statistics and metrics."""
    total_points: int
    total_distance_m: float
    estimated_time_min: float
    coverage_percentage: float



class TrajectoryResponse(BaseModel):
    """Trajectory retrieval response."""
    id: int
    wall_width: float
    wall_height: float
    obstacles: List[Dict[str, Any]]
    tool_width: float
    coverage_margin: float
    trajectory_points: List[List[float]]
    metrics: PathMetrics
    timestamp: str



class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database: str
    timestamp: str



# --- DATABASE MANAGEMENT ---


def get_db_connection() -> sqlite3.Connection:
    """Create optimized SQLite connection."""
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    # Use configurable cache_size (KB). Negative value instructs SQLite to use
    # page cache size in KB. Default is settings.cache_size (64000 KB -> ~64MB).
    try:
        cache_kb = int(getattr(settings, 'cache_size', 64000))
        if cache_kb and cache_kb > 0:
            conn.execute(f'PRAGMA cache_size = -{cache_kb}')
    except Exception:
        # Fall back to a safe default
        conn.execute('PRAGMA cache_size = -64000')

    conn.execute('PRAGMA temp_store = MEMORY')
    # Ensure foreign keys cascade deletions for trajectory points
    try:
        conn.execute('PRAGMA foreign_keys = ON')
    except Exception:
        pass
    # Optional mmap_size (only set when explicitly configured > 0)
    try:
        mmap_size = int(getattr(settings, 'mmap_size', 0))
        if mmap_size and mmap_size > 0:
            conn.execute(f'PRAGMA mmap_size = {mmap_size}')
    except Exception:
        # Ignore if unsupported on host
        pass
    conn.row_factory = sqlite3.Row
    return conn



def init_db():
    """Initialize database schema with optimized indexes."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wall_width REAL NOT NULL,
                wall_height REAL NOT NULL,
                obstacles TEXT NOT NULL,
                tool_width REAL NOT NULL,
                coverage_margin REAL NOT NULL,
                total_distance REAL,
                estimated_time REAL,
                coverage_percentage REAL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Separate table for trajectory points to allow batched inserts and smaller
        # read payloads. This helps performance when trajectories are large.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trajectory_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trajectory_id INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                FOREIGN KEY(trajectory_id) REFERENCES trajectories(id) ON DELETE CASCADE
            );
        ''')
        
        # Optimized composite indexes
        conn.execute('CREATE INDEX IF NOT EXISTS idx_wall_dimensions ON trajectories (wall_width, wall_height);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_desc ON trajectories (timestamp DESC);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tool_width ON trajectories (tool_width);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_points_traj ON trajectory_points (trajectory_id, seq);')
        
        # Enable auto-vacuum
        conn.execute('PRAGMA auto_vacuum = INCREMENTAL;')
        conn.commit()
        
        logger.info(f"[OK] Database initialized at {settings.db_path}")
        # Launch a background maintenance task to checkpoint WAL and periodically VACUUM
        def _maintenance_loop():
            conn = get_db_connection()
            try:
                last_vacuum = time.time()
                checkpoint_interval = getattr(settings, 'checkpoint_interval_seconds', 300)
                vacuum_interval = getattr(settings, 'vacuum_interval_seconds', 3600)
                while True:
                    try:
                        # WAL checkpoint
                        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                        conn.commit()
                    except Exception:
                        pass

                    # Periodic VACUUM (infrequent, heavy operation)
                    now_t = time.time()
                    if vacuum_interval and (now_t - last_vacuum) >= vacuum_interval:
                        try:
                            conn.execute('VACUUM')
                            conn.commit()
                            last_vacuum = now_t
                            logger.info('[MAINT] Performed VACUUM')
                        except Exception:
                            pass

                    # Sleep for the configured interval
                    time.sleep(checkpoint_interval)
            finally:
                conn.close()

        # Start maintenance task in background thread unless running under pytest
        try:
            import threading, sys, os
            if 'PYTEST_CURRENT_TEST' not in os.environ and 'pytest' not in sys.modules:
                maint_thread = threading.Thread(target=_maintenance_loop, daemon=True)
                maint_thread.start()
                # Store thread in app state if available
                try:
                    app.state.db_maintenance_task = maint_thread
                except Exception:
                    pass
        except Exception:
            # Non-fatal if we cannot spawn background thread
            pass
    except Exception as e:
        logger.error(f"[ERROR] Database initialization failed: {e}")
        raise
    finally:
        conn.close()



# --- PATH PLANNING ALGORITHM ---


def is_point_obstructed(x: Decimal, y: Decimal, obstacles: List[Obstacle], tool_radius: Decimal) -> bool:
    """Check if point collides with obstacle exclusion zone."""
    for obs in obstacles:
        # Ensure all values are Decimals
        obs_x = obs.x if isinstance(obs.x, Decimal) else Decimal(str(obs.x))
        obs_y = obs.y if isinstance(obs.y, Decimal) else Decimal(str(obs.y))
        obs_width = obs.width if isinstance(obs.width, Decimal) else Decimal(str(obs.width))
        obs_height = obs.height if isinstance(obs.height, Decimal) else Decimal(str(obs.height))
        
        min_x = obs_x - tool_radius
        max_x = obs_x + obs_width + tool_radius
        min_y = obs_y - tool_radius
        max_y = obs_y + obs_height + tool_radius
        
        if min_x <= x <= max_x and min_y <= y <= max_y:
            return True
    return False



def calculate_path_metrics(path: List[List[float]], wall_area: float) -> PathMetrics:
    """Calculate comprehensive path statistics."""
    if not path:
        return PathMetrics(
            total_points=0,
            total_distance_m=0.0,
            estimated_time_min=0.0,
            coverage_percentage=0.0
        )
    
    # Calculate total distance
    total_distance = 0.0
    for i in range(1, len(path)):
        dx = path[i][0] - path[i-1][0]
        dy = path[i][1] - path[i-1][1]
        total_distance += (dx**2 + dy**2)**0.5
    
    # Estimated time (assuming 0.5 m/s robot speed)
    robot_speed = 0.5  # m/s
    estimated_time = (total_distance / robot_speed) / 60  # minutes
    
    # Coverage estimation (simplified)
    coverage_percentage = min(100.0, (len(path) * 0.001 / wall_area) * 100)
    
    return PathMetrics(
        total_points=len(path),
        total_distance_m=round(total_distance, 2),
        estimated_time_min=round(estimated_time, 2),
        coverage_percentage=round(coverage_percentage, 2)
    )



def generate_coverage_path(plan: WallPlanRequest, progress_callback: Optional[Callable[[int, int], None]] = None) -> tuple[List[List[float]], PathMetrics]:
    """
    Generate optimized boustrophedon (snake) coverage path.
    Returns trajectory points and metrics.
    Optional `progress_callback(percent:int, points:int)` is called from the
    planner thread to report progress; the callback must be thread-safe or
    schedule into the event loop (e.g., loop.call_soon_threadsafe).
    """
    try:
        # Ensure all values are Decimals
        W = plan.wall_width if isinstance(plan.wall_width, Decimal) else Decimal(str(plan.wall_width))
        H = plan.wall_height if isinstance(plan.wall_height, Decimal) else Decimal(str(plan.wall_height))
        T = plan.tool_width if isinstance(plan.tool_width, Decimal) else Decimal(str(plan.tool_width))
        M = plan.coverage_margin if isinstance(plan.coverage_margin, Decimal) else Decimal(str(plan.coverage_margin))

        obstacles = plan.obstacles

        step_x = T * Decimal("0.9")  # 10% overlap for better coverage
        tool_half = T / Decimal("2.0")

        path: List[List[float]] = []
        current_x = M + tool_half
        total_width = float((W - M - tool_half) - (M + tool_half)) if (W - 2*M - tool_half*2) > 0 else 0.0
        point_counter = 0

        while current_x < W - M - tool_half:
            # Alternate direction for snake pattern
            col_points = [p for p in path if abs(p[0] - float(current_x)) < 0.001]
            if len(col_points) % 2 == 0:
                # Bottom to top
                y_start, y_end, dy = (M + tool_half, H - M - tool_half, step_x / Decimal("4.0"))
            else:
                # Top to bottom
                y_start, y_end, dy = (H - M - tool_half, M + tool_half, -step_x / Decimal("4.0"))

            current_y = y_start

            while (dy > 0 and current_y <= y_end) or (dy < 0 and current_y >= y_end):
                if not is_point_obstructed(current_x, current_y, obstacles, tool_half):
                    path.append([float(current_x), float(current_y)])
                    point_counter += 1
                    # report progress every 500 points
                    if progress_callback and (point_counter % 500 == 0):
                        try:
                            percent = 0
                            if total_width > 0:
                                percent = int(((float(current_x) - float(M + tool_half)) / total_width) * 100)
                                percent = max(0, min(100, percent))
                            progress_callback(percent, point_counter)
                        except Exception:
                            pass
                current_y += dy

            current_x += step_x

        # Calculate metrics
        wall_area = float(W * H)
        metrics = calculate_path_metrics(path, wall_area)

        logger.info(f"[OK] Path generated: {metrics.total_points} points, {metrics.total_distance_m}m")
        return path, metrics

    except Exception as e:
        logger.error(f"[ERROR] Path planning error: {e}")
        raise HTTPException(status_code=500, detail=f"Path planning failed: {str(e)}")


@app.websocket("/ws/plan")
async def websocket_plan(ws: WebSocket):
    """WebSocket endpoint: accept a plan JSON, stream progress and final result."""
    await ws.accept()
    try:
        payload = await ws.receive_json()
    except Exception:
        await ws.close(code=1003)
        return

    # Normalize payload keys (support both 'width' and 'wall_width')
    if 'width' in payload and 'wall_width' not in payload:
        payload['wall_width'] = payload.pop('width')
    if 'height' in payload and 'wall_height' not in payload:
        payload['wall_height'] = payload.pop('height')

    # Normalize obstacles
    obs_list = payload.get('obstacles', [])
    normalized = []
    for o in obs_list:
        if 'w' in o and 'width' not in o:
            o['width'] = o.pop('w')
        if 'h' in o and 'height' not in o:
            o['height'] = o.pop('h')
        normalized.append(o)
    payload['obstacles'] = normalized

    try:
        plan = WallPlanRequest(**payload)
    except Exception as e:
        await ws.send_json({"type": "error", "detail": str(e)})
        await ws.close()
        return

    loop = asyncio.get_running_loop()
    progress_queue: asyncio.Queue = asyncio.Queue()

    # thread-safe callback to push progress into asyncio queue
    def progress_cb(percent: int, points: int):
        try:
            loop.call_soon_threadsafe(progress_queue.put_nowait, {"type": "progress", "percent": percent, "points": points})
        except Exception:
            pass

    def run_planner():
        return generate_coverage_path(plan, progress_callback=progress_cb)

    planner_future = loop.run_in_executor(None, run_planner)

    try:
        while True:
            # wait for either planner completion or a progress item
            done, pending = await asyncio.wait(
                [planner_future, asyncio.create_task(progress_queue.get())],
                return_when=asyncio.FIRST_COMPLETED
            )

            if planner_future in done:
                path, metrics = planner_future.result()
                await ws.send_json({"type": "result", "metrics": metrics.model_dump(), "path_points": len(path)})
                break
            else:
                for task in done:
                    if task is not planner_future:
                        msg = task.result()
                        await ws.send_json(msg)
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        await ws.close()



# --- MIDDLEWARE ---

# Simple in-memory rate limiter (per-IP sliding window). This is intentionally
# lightweight for development/testing; for production use a redis-backed
# limiter or a vetted library (e.g., `slowapi` with Redis/FastAPI integration).
_rate_limits: Dict[str, List[float]] = {}
RATE_LIMIT_WINDOW = getattr(settings, 'rate_limit_window_seconds', 60)
RATE_LIMIT_MAX = getattr(settings, 'rate_limit_max_requests', 60)


@app.middleware("http")
async def enforce_limits(request: Request, call_next):
    """Enforce request size and a simple per-IP rate limit."""
    # Request size limit (Content-Length) if provided
    max_size = getattr(settings, 'max_request_size_bytes', 10 * 1024 * 1024)  # 10MB default
    cl = request.headers.get('content-length')
    if cl:
        try:
            if int(cl) > max_size:
                return JSONResponse(status_code=413, content={"detail": "Request payload too large"})
        except ValueError:
            pass

    # Rate limiting by client IP
    client = request.client.host if request.client else 'unknown'
    now = time.time()
    window = _rate_limits.setdefault(client, [])
    # Remove timestamps outside window
    while window and window[0] <= now - RATE_LIMIT_WINDOW:
        window.pop(0)
    if len(window) >= RATE_LIMIT_MAX:
        # Too many requests
        return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    window.append(now)

    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing information."""
    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    logger.info(
        f"[REQUEST] {request.method} {request.url.path} | "
        f"Status: {response.status_code} | "
        f"Time: {process_time:.4f}s | "
        f"Client: {request.client.host if request.client else 'unknown'}"
    )

    return response



# --- API ENDPOINTS ---


@app.get("/", response_model=HealthResponse, tags=["Health"])
async def root():
    """Root endpoint with system status."""
    return {
        "status": "operational",
        "version": "2.0.0",
        "database": settings.db_path,
        "timestamp": datetime.now(timezone.utc).isoformat() # <--- CORRECTION: Changed datetime.UTC to timezone.utc
    }



@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Test database connectivity
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "version": "2.0.0",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat() # <--- CORRECTION: Changed datetime.utcnow() to timezone.utc
    }



@app.post("/api/v1/plan", status_code=201, response_model=Dict[str, Any], tags=["Planning"])
@rate_limit_decorator("10/minute")
async def create_plan(plan: WallPlanRequest, auth=Depends(require_auth)):
    """
    Generate and store a coverage path plan.
    
    - **wall_width**: Wall width in meters (positive)
    - **wall_height**: Wall height in meters (positive)
    - **obstacles**: List of rectangular obstacles
    - **tool_width**: Robot tool width in meters
    - **coverage_margin**: Safety margin from edges/obstacles
    
    Returns the stored trajectory ID and metrics.
    """
    # Generate path asynchronously
    path, metrics = await asyncio.to_thread(generate_coverage_path, plan)
    
    # Store in database: insert trajectory metadata first, then batch-insert points.
    def db_insert_batched(batch_size: int = 1000):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            obstacles_json = json.dumps([obs.model_dump() for obs in plan.obstacles], default=str)

            # Insert metadata into trajectories
            cursor.execute(
                """
                INSERT INTO trajectories 
                (wall_width, wall_height, obstacles, tool_width, coverage_margin, 
                 total_distance, estimated_time, coverage_percentage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(plan.wall_width),
                    float(plan.wall_height),
                    obstacles_json,
                    float(plan.tool_width),
                    float(plan.coverage_margin),
                    metrics.total_distance_m,
                    metrics.estimated_time_min,
                    metrics.coverage_percentage
                )
            )
            traj_id = cursor.lastrowid

            # Prepare batched insertion of points
            if path:
                points = [(traj_id, idx, float(p[0]), float(p[1])) for idx, p in enumerate(path)]

                for i in range(0, len(points), batch_size):
                    chunk = points[i:i+batch_size]
                    cursor.executemany(
                        "INSERT INTO trajectory_points (trajectory_id, seq, x, y) VALUES (?, ?, ?, ?)",
                        chunk
                    )

            conn.commit()
            return traj_id
        finally:
            conn.close()

    new_id = await asyncio.to_thread(db_insert_batched)
    
    logger.info(f"[OK] Trajectory #{new_id} created successfully")
    # Publish event to MQTT broker if enabled
    try:
        mqtt_client = getattr(app.state, 'mqtt_client', None)
        if mqtt_client is not None:
            payload = json.dumps({
                "id": new_id,
                "metrics": metrics.model_dump(),
                "wall_width": float(plan.wall_width),
                "wall_height": float(plan.wall_height),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            mqtt_client.publish(settings.mqtt_topic, payload)
            logger.debug(f"[MQTT] Published trajectory #{new_id} to {settings.mqtt_topic}")
    except Exception as e:
        logger.warning(f"[WARN] Failed to publish MQTT event for trajectory #{new_id}: {e}")
    
    return {
        "id": new_id,
        "message": "Coverage plan generated and stored successfully",
        "metrics": metrics.model_dump()
    }



@app.get("/api/v1/trajectory/{plan_id}", response_model=TrajectoryResponse, tags=["Planning"])
async def get_trajectory(plan_id: int):
    """Retrieve a stored trajectory by ID."""
    
    def db_fetch():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trajectories WHERE id = ?", (plan_id,))
            row = cursor.fetchone()
            if row is None:
                return None

            # Fetch points separately and attach
            cursor.execute("SELECT seq, x, y FROM trajectory_points WHERE trajectory_id = ? ORDER BY seq ASC", (plan_id,))
            pts = cursor.fetchall()
            # Convert sqlite rows into simple list of [x,y]
            points = [[float(r['x']), float(r['y'])] for r in pts]

            # Return combined result as dict-like row
            result = dict(row)
            result['trajectory_points'] = points
            return result
        finally:
            conn.close()
    
    row = await asyncio.to_thread(db_fetch)
    
    if row is None:
        logger.warning(f"[WARN] Trajectory #{plan_id} not found")
        raise HTTPException(status_code=404, detail=f"Trajectory {plan_id} not found")

    data = row if isinstance(row, dict) else dict(row)
    data['obstacles'] = json.loads(data['obstacles'])
    
    # Construct metrics
    data['metrics'] = PathMetrics(
        total_points=len(data['trajectory_points']),
        total_distance_m=data.get('total_distance', 0.0) or 0.0,
        estimated_time_min=data.get('estimated_time', 0.0) or 0.0,
        coverage_percentage=data.get('coverage_percentage', 0.0) or 0.0
    )
    
    return data



@app.get("/api/v1/trajectories", tags=["Planning"])
async def list_trajectories(
    limit: int = 10,
    offset: int = 0,
    min_width: Optional[float] = None,
    max_width: Optional[float] = None
):
    """
    List recent trajectories with optional filtering.
    
    - **limit**: Maximum number of results (default: 10)
    - **offset**: Pagination offset (default: 0)
    - **min_width**: Filter by minimum wall width
    - **max_width**: Filter by maximum wall width
    """
    
    def db_fetch_all():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            query = "SELECT id, wall_width, wall_height, total_distance, timestamp FROM trajectories WHERE 1=1"
            params = []
            
            if min_width is not None:
                query += " AND wall_width >= ?"
                params.append(min_width)
            
            if max_width is not None:
                query += " AND wall_width <= ?"
                params.append(max_width)
            
            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Get total count
            count_query = "SELECT COUNT(*) as total FROM trajectories WHERE 1=1"
            count_params = []
            if min_width is not None:
                count_query += " AND wall_width >= ?"
                count_params.append(min_width)
            if max_width is not None:
                count_query += " AND wall_width <= ?"
                count_params.append(max_width)
            
            cursor.execute(count_query, count_params)
            total = cursor.fetchone()['total']
            
            return [dict(row) for row in rows], total
        finally:
            conn.close()
    
    plans, total = await asyncio.to_thread(db_fetch_all)
    
    return {
        "plans": plans,
        "count": len(plans),
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(plans)) < total
    }



@app.delete("/api/v1/trajectory/{plan_id}", status_code=204, tags=["Planning"])
@rate_limit_decorator("20/minute")
async def delete_trajectory(plan_id: int, auth=Depends(require_auth)):
    """Delete a trajectory by ID."""
    
    def db_delete():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trajectories WHERE id = ?", (plan_id,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            conn.close()
    
    deleted = await asyncio.to_thread(db_delete)
    
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Trajectory {plan_id} not found")
    
    logger.info(f"[DELETE] Trajectory #{plan_id} deleted")
    return None



# --- CORS CONFIGURATION ---


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"Static files directory not found: {e}")



# --- MAIN RUNNER ---


if __name__ == "__main__":
    logger.info(f"[START] Starting server on {settings.api_host}:{settings.api_port}")
    uvicorn.run(
        "robot_control_system:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        workers=1,  # Use 1 for development, settings.api_workers for production
        log_level=settings.log_level.lower()
    )