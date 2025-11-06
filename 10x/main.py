import json
import logging
import sqlite3
import time
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager # New import for modern FastAPI events

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# --- 1. Configuration and Setup ---

DATABASE_FILE = "robot_control.db"

# Configure Logging (Detailed and time-aware)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("RobotControl")


# --- 2. Database Management ---

def init_db():
    """Initializes the SQLite database schema."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trajectories (
            id INTEGER PRIMARY KEY,
            wall_width REAL NOT NULL,
            wall_height REAL NOT NULL,
            step_size REAL NOT NULL,
            obstacle_data TEXT,
            trajectory_json TEXT NOT NULL,
            process_time_ms REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Optimization: Index on creation time for historical lookups (fastest retrieval of recent data)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON trajectories (created_at);")
    conn.commit()
    conn.close()

def get_db_connection():
    """Dependency to provide a database connection."""
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        yield conn
    finally:
        conn.close()


# --- 3. Pydantic Models for Robustness ---

class Obstacle(BaseModel):
    """Defines a rectangular obstacle."""
    x: float = Field(..., description="X coordinate of the obstacle corner (meters).")
    y: float = Field(..., description="Y coordinate of the obstacle corner (meters).")
    width: float = Field(..., description="Width of the obstacle (meters).")
    height: float = Field(..., description="Height of the obstacle (meters).")

class TrajectoryGenerationRequest(BaseModel):
    """Input schema for path planning."""
    wall_width: float = Field(5.0, gt=0, description="Wall width in meters.")
    wall_height: float = Field(5.0, gt=0, description="Wall height in meters.")
    step_size: float = Field(0.1, gt=0, description="Distance between parallel scan lines in meters (e.g., roller width).")
    obstacles: List[Obstacle] = Field(
        [Obstacle(x=2.0, y=2.0, width=0.25, height=0.25)],
        description="List of rectangular obstacles."
    )

class TrajectoryPoint(BaseModel):
    """A single point in the robot's trajectory."""
    x: float
    y: float
    t: float # Time elapsed

class TrajectoryResponse(BaseModel):
    """Response schema for a stored trajectory."""
    id: int
    wall_width: float
    wall_height: float
    step_size: float
    obstacles: List[Obstacle]
    trajectory: List[TrajectoryPoint]
    process_time_ms: float
    created_at: str

class TrajectorySummary(BaseModel):
    """A minimal summary for listing recent trajectories."""
    id: int
    wall_size: str
    process_time_ms: float
    created_at: str

class DBStatsResponse(BaseModel):
    """Model for sophisticated database monitoring endpoint."""
    total_trajectories: int
    avg_process_time_ms: float
    fastest_plan_ms: Optional[float]
    slowest_plan_ms: Optional[float]
    latest_run_id: Optional[int]


# --- 4. Middleware (Server-Intensive Monitoring) ---

class TimingMiddleware(BaseHTTPMiddleware):
    """Custom middleware to log request processing time."""
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time-ms"] = str(round(process_time * 1000, 3))
        logger.info(
            f"Request finished: {request.method} {request.url.path} | "
            f"Status: {response.status_code} | "
            f"Response Time: {process_time:.4f}s"
        )
        return response


# --- 6. FastAPI App Initialization ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events (startup/shutdown)."""
    # Startup: Initialize the database
    init_db()
    logger.info("Database initialized and ready.")
    yield
    # Shutdown (optional cleanup can go here)
    logger.info("Application shutdown.")


app = FastAPI(
    title="Autonomous Wall Finishing Robot Control System",
    lifespan=lifespan # Use the new lifespan context manager
)
app.add_middleware(TimingMiddleware) # Add the custom timing middleware

# ADDED CORS MIDDLEWARE: Allow requests from all origins during local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allows all headers
)


# --- 5. Path Planning Logic (Boustrophedon/Raster Scan) ---

def is_in_obstacle(x: float, y: float, obstacles: List[Obstacle]) -> bool:
    """Checks if a point (x, y) is inside any obstacle."""
    for obs in obstacles:
        # Check if the point is within the obstacle's bounding box
        if (obs.x <= x < obs.x + obs.width and
                obs.y <= y < obs.y + obs.height): 
            return True
    return False

def generate_coverage_path(req: TrajectoryGenerationRequest) -> Dict[str, Any]:
    """
    Generates an optimized Boustrophedon (Raster Scan) coverage path,
    handling obstacle avoidance by skipping/lifting the tool over the obstacle area.
    """
    start_time = time.perf_counter()
    W, H, S = req.wall_width, req.wall_height, req.step_size
    obstacles = req.obstacles

    trajectory = []
    current_time = 0.0
    y = S / 2  # Start half a step size from the bottom edge
    direction = 1  # 1 for right, -1 for left

    # Define a simplified step time (robot speed proxy)
    TIME_PER_METER = 0.5  # seconds per meter

    while y < H:
        # Determine the x-scan limits based on direction
        x_start = S / 2 if direction == 1 else W - S / 2
        x_end = W - S / 2 if direction == 1 else S / 2
        
        # Micro-steps for smooth visualization: 10 steps per Step Size width
        x_step = S * direction / 10 

        x = x_start
        
        # Horizontal scan loop
        while (direction == 1 and x < x_end + abs(x_step)/2) or (direction == -1 and x > x_end - abs(x_step)/2):
            
            # Clamp X within bounds
            x_clamped = max(S/2, min(W - S/2, x))
            
            is_obs = is_in_obstacle(x_clamped, y, obstacles)
            
            # If not in an obstacle, record the point
            if not is_obs:
                trajectory.append(TrajectoryPoint(x=round(x_clamped, 4), y=round(y, 4), t=round(current_time, 4)))
                current_time += abs(x_step) * TIME_PER_METER
            else:
                # Still increment time to account for travel over the obstacle
                current_time += abs(x_step) * TIME_PER_METER

            x += x_step

        # Turnaround movement (vertical step)
        y += S
        
        # Add turnaround time if we are not past the wall height
        if y < H:
            current_time += S * TIME_PER_METER * 2 
        
        # Switch direction for the next row
        direction *= -1

    process_time_ms = (time.perf_counter() - start_time) * 1000
    
    # Store the complex path points as a JSON string for database insertion (IO efficiency)
    trajectory_json = json.dumps([p.model_dump() for p in trajectory])

    return {
        "wall_width": W,
        "wall_height": H,
        "step_size": S,
        "obstacle_data": json.dumps([o.model_dump() for o in obstacles]),
        "trajectory_json": trajectory_json,
        "process_time_ms": process_time_ms
    }


# --- 7. API Endpoints ---

@app.post("/generate", response_model=TrajectoryResponse)
def generate_and_save_trajectory(
    req: TrajectoryGenerationRequest,
    conn: sqlite3.Connection = Depends(get_db_connection) 
):
    """
    Generates a new coverage path based on user input, saves it to the database,
    and returns the saved trajectory data.
    """
    # 1. Generate path
    data = generate_coverage_path(req)

    # 2. Save to DB
    # The 'conn' object is now directly the sqlite3 Connection, allowing .cursor() call.
    try:
        cursor = conn.cursor() 
        cursor.execute(
            """
            INSERT INTO trajectories (
                wall_width, wall_height, step_size, obstacle_data, trajectory_json, process_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data["wall_width"],
                data["wall_height"],
                data["step_size"],
                data["obstacle_data"],
                data["trajectory_json"],
                data["process_time_ms"],
            ),
        )
        conn.commit()
        last_id = cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Database error during insert: {e}")
        raise HTTPException(status_code=500, detail="Failed to save trajectory to database.")

    # 3. Prepare response
    obstacles = json.loads(data["obstacle_data"])
    trajectory = json.loads(data["trajectory_json"])

    return TrajectoryResponse(
        id=last_id,
        wall_width=data["wall_width"],
        wall_height=data["wall_height"],
        step_size=data["step_size"],
        obstacles=obstacles,
        trajectory=trajectory,
        process_time_ms=data["process_time_ms"],
        created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

@app.get("/trajectory/{trajectory_id}", response_model=TrajectoryResponse)
def get_trajectory(trajectory_id: int, conn: sqlite3.Connection = Depends(get_db_connection)):
    """Retrieves a previously saved trajectory by its ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trajectories WHERE id = ?", (trajectory_id,))
    row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Trajectory not found.")

    columns = [
        "id", "wall_width", "wall_height", "step_size", "obstacle_data",
        "trajectory_json", "process_time_ms", "created_at"
    ]
    data = dict(zip(columns, row))

    data["obstacles"] = json.loads(data.pop("obstacle_data"))
    data["trajectory"] = json.loads(data.pop("trajectory_json"))

    return TrajectoryResponse(**data)

@app.get("/trajectories/recent", response_model=List[TrajectorySummary])
def list_recent_trajectories(conn: sqlite3.Connection = Depends(get_db_connection)):
    """
    Lists the 10 most recently generated trajectories, optimized by indexed timestamp.
    """
    cursor = conn.cursor()
    # Optimized query using the indexed column
    cursor.execute(
        """
        SELECT id, wall_width, wall_height, process_time_ms, created_at 
        FROM trajectories 
        ORDER BY created_at DESC 
        LIMIT 10
        """
    )
    rows = cursor.fetchall()
    
    summaries = []
    for row in rows:
        summaries.append(TrajectorySummary(
            id=row[0],
            wall_size=f"{row[1]}m x {row[2]}m",
            process_time_ms=row[3],
            created_at=row[4]
        ))
    
    return summaries

@app.get("/db/stats", response_model=DBStatsResponse)
def get_db_statistics(conn: sqlite3.Connection = Depends(get_db_connection)):
    """
    Highly optimized and robust endpoint for comprehensive database and system monitoring.
    """
    cursor = conn.cursor()

    # 1. Total Count and Latest ID
    cursor.execute("SELECT COUNT(id), MAX(id) FROM trajectories")
    count, latest_id = cursor.fetchone()
    
    if count == 0:
        return DBStatsResponse(
            total_trajectories=0,
            avg_process_time_ms=0.0,
            fastest_plan_ms=None,
            slowest_plan_ms=None,
            latest_run_id=None
        )

    # 2. Aggregates (AVG, MIN, MAX)
    cursor.execute(
        "SELECT AVG(process_time_ms), MIN(process_time_ms), MAX(process_time_ms) FROM trajectories"
    )
    avg_time, min_time, max_time = cursor.fetchone()
    
    return DBStatsResponse(
        total_trajectories=count,
        avg_process_time_ms=round(avg_time, 2),
        fastest_plan_ms=round(min_time, 2),
        slowest_plan_ms=round(max_time, 2),
        latest_run_id=latest_id
    )

@app.get("/status")
def get_status():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "Wall Robot Control System"}

@app.get("/")
def read_root():
    return JSONResponse(content={"message": "Use the /docs endpoint or the generated index.html file."})