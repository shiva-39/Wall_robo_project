import sqlite3
import json
import logging
import time
from decimal import Decimal, getcontext
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import asyncio
from concurrent.futures import ThreadPoolExecutor

# --- 0. CONFIGURATION & INITIALIZATION ---

# Set Decimal precision high for engineering/robotics computations (Overkill detail)
getcontext().prec = 50

# Database path and connection setup
DB_PATH = "robot_trajectories.db"
# Use a separate thread pool for SQLite I/O to avoid blocking the main event loop
executor = ThreadPoolExecutor(max_workers=5)

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Wall-Finishing Robot Control API", version="1.0.1")


# --- 1. DATA MODELS (Pydantic) ---

class Obstacle(BaseModel):
    """Defines a rectangular obstacle on the wall."""
    id: str
    x: Decimal = Field(..., description="Bottom-left X coordinate (m)")
    y: Decimal = Field(..., description="Bottom-left Y coordinate (m)")
    width: Decimal = Field(..., gt=0, description="Width (m)")
    height: Decimal = Field(..., gt=0, description="Height (m)")

    class Config:
        # Allows Decimal types in Pydantic models
        json_encoders = {Decimal: str}

class WallPlanRequest(BaseModel):
    """Input schema for path planning."""
    wall_width: Decimal = Field(..., gt=0, description="Wall width (m)")
    wall_height: Decimal = Field(..., gt=0, description="Wall height (m)")
    obstacles: List[Obstacle] = Field(default_factory=list, description="List of obstacles")
    tool_width: Decimal = Field(default=Decimal("0.05"), gt=0, description="Robot tool/brush width (m)")
    coverage_margin: Decimal = Field(default=Decimal("0.01"), ge=0, description="Safety margin from edges/obstacles (m)")

    class Config:
        json_encoders = {Decimal: str}

class TrajectoryResponse(BaseModel):
    """Output schema for a stored trajectory."""
    id: int
    wall_width: float
    wall_height: float
    obstacles: List[Dict[str, Any]]
    tool_width: float
    coverage_margin: float
    trajectory_points: List[List[float]]
    timestamp: str

# --- 2. DATABASE MANAGEMENT ---

def get_db_connection() -> sqlite3.Connection:
    """Creates and returns a highly-optimized SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    # Overkill Optimization 1: Enable Write-Ahead Logging (WAL) for better concurrency
    conn.execute('PRAGMA journal_mode = WAL')
    # Overkill Optimization 2: Set synchronous=NORMAL to reduce commit latency
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates the trajectory table."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wall_width REAL NOT NULL,
                wall_height REAL NOT NULL,
                obstacles TEXT,
                tool_width REAL NOT NULL,
                coverage_margin REAL NOT NULL,
                trajectory_points TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Overkill Optimization 3: Add index for faster lookups by dimension/timestamp
        conn.execute('CREATE INDEX IF NOT EXISTS idx_wall_size ON trajectories (wall_width, wall_height);')
        conn.commit()
    finally:
        conn.close()

# Ensure the database is initialized on startup
init_db()

# --- 3. PATH PLANNING LOGIC (The Core Algorithm) ---

def is_point_obstructed(x: Decimal, y: Decimal, obstacles: List[Obstacle], tool_radius: Decimal) -> bool:
    """Checks if a point is within the exclusion zone of any obstacle."""
    for obs in obstacles:
        # Calculate the bounding box for the tool path around the obstacle
        min_x = obs.x - tool_radius
        max_x = obs.x + obs.width + tool_radius
        min_y = obs.y - tool_radius
        max_y = obs.y + obs.height + tool_radius

        if min_x <= x <= max_x and min_y <= y <= max_y:
            return True
    return False

def generate_coverage_path(plan: WallPlanRequest) -> List[List[float]]:
    """
    Generates a high-precision, optimized raster (snake) coverage path.
    Uses Decimal for all internal calculations.
    """
    try:
        W, H = plan.wall_width, plan.wall_height
        T = plan.tool_width
        M = plan.coverage_margin
        obstacles = plan.obstacles
        
        # Tool movement step (should be less than tool width to ensure overlap)
        step_x = T
        # Half tool width (radius) for center point offset
        tool_half = T / Decimal("2.0")

        path = []
        
        # Start X (Offset by margin + half tool width)
        current_x = M + tool_half
        
        # Main loop: Iterate across the width of the wall
        while current_x < W - M - tool_half:
            # Determine direction of travel (Snake Pattern)
            if len(path) % 2 == 0:
                # Move bottom-to-top (Y increasing)
                y_start = M + tool_half
                y_end = H - M - tool_half
                dy = step_x / Decimal("4.0") # Smaller step for Y for higher resolution
                
                current_y = y_start
                while current_y <= y_end:
                    # Check for obstruction before adding point
                    if not is_point_obstructed(current_x, current_y, obstacles, tool_half):
                        path.append([float(current_x), float(current_y)])
                    current_y += dy
                    
            else:
                # Move top-to-bottom (Y decreasing)
                y_start = H - M - tool_half
                y_end = M + tool_half
                dy = -step_x / Decimal("4.0")
                
                current_y = y_start
                while current_y >= y_end:
                    if not is_point_obstructed(current_x, current_y, obstacles, tool_half):
                        path.append([float(current_x), float(current_y)])
                    current_y += dy
            
            # Move to the next column
            current_x += step_x
            
        return path
        
    except Exception as e:
        logger.error(f"Path planning error: {e}")
        raise

# --- 4. CUSTOM MIDDLEWARE (Overkill Detail 4: Request Timing) ---

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Measures and logs the processing time for each request."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    # Detailed logging (Overkill Detail 5: Response Timing)
    logger.info(
        f"Request: {request.method} {request.url.path} | "
        f"Status: {response.status_code} | "
        f"Time: {process_time:.4f}s"
    )
    return response

# --- 5. API ENDPOINTS ---

@app.post("/plan", status_code=201)
async def create_new_plan(plan: WallPlanRequest):
    """
    Generates a coverage path based on wall and obstacle parameters,
    stores it in the SQLite database, and returns the ID.
    """
    # Run the computationally intensive path planning in the background thread
    # Overkill Detail 6: Use asyncio.to_thread for non-blocking computation
    path = await asyncio.to_thread(generate_coverage_path, plan)
    
    # Store result in DB (also runs in background thread)
    def db_insert():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # FIX: The original code attempted to call .json() on a list object.
            # We must manually convert the list of Pydantic models (Obstacle) into dictionaries 
            # and then serialize the list to a JSON string for SQLite storage.
            # The 'default=str' ensures Decimal objects are correctly converted to strings during serialization.
            obstacles_json = json.dumps([obs.dict() for obs in plan.obstacles], default=str)
            
            cursor.execute(
                """
                INSERT INTO trajectories 
                (wall_width, wall_height, obstacles, tool_width, coverage_margin, trajectory_points)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    float(plan.wall_width), 
                    float(plan.wall_height), 
                    obstacles_json, # <-- FIXED: Now a valid JSON string
                    float(plan.tool_width), 
                    float(plan.coverage_margin),
                    json.dumps(path)
                )
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    new_id = await asyncio.to_thread(db_insert)
    
    logger.info(f"New trajectory plan created with ID: {new_id}")
    return {"id": new_id, "message": "Coverage plan generated and stored successfully."}

@app.get("/trajectory/{plan_id}", response_model=TrajectoryResponse)
async def get_trajectory(plan_id: int):
    """Retrieves a stored trajectory plan by ID."""
    
    def db_fetch():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trajectories WHERE id = ?", (plan_id,))
            row = cursor.fetchone()
            return row
        finally:
            conn.close()

    row = await asyncio.to_thread(db_fetch)
    
    if row is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    
    # Convert sqlite3.Row to dictionary and parse JSON fields
    data = dict(row)
    data['obstacles'] = json.loads(data['obstacles'])
    data['trajectory_points'] = json.loads(data['trajectory_points'])
    
    return data

@app.get("/trajectories")
async def list_trajectories(limit: int = 10, offset: int = 0):
    """Lists recent trajectory plans."""
    
    def db_fetch_all():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Order by ID descending for most recent, and apply limits
            cursor.execute("SELECT id, wall_width, wall_height, timestamp FROM trajectories ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    recent_plans = await asyncio.to_thread(db_fetch_all)
    return {"plans": recent_plans, "count": len(recent_plans)}

# --- 6. CORS & STATIC FILES (Minimal) ---

# Allow the frontend (HTML) to access the API (CORS is mandatory for this setup)
from starlette.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 7. FASTAPI TEST CLIENT (For manual testing purposes) ---

def run_tests():
    """
    Basic API tests using FastAPI's built-in TestClient.
    NOTE: This requires 'pytest' and 'httpx' to be installed.
    """
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        logger.warning("TestClient dependencies not installed. Skipping tests.")
        return

    client = TestClient(app)
    logger.info("\n--- Running API Tests ---")

    # Sample Case from the assignment (5m x 5m wall, 0.25m x 0.25m window)
    test_plan_data = {
        "wall_width": 5.0,
        "wall_height": 5.0,
        "tool_width": 0.1, # A more realistic 10cm tool
        "coverage_margin": 0.05,
        "obstacles": [
            {"id": "window-1", "x": 2.0, "y": 2.0, "width": 0.5, "height": 0.5}
        ]
    }

    # Test 1: POST /plan - Create a new plan
    start_time = time.time()
    response = client.post("/plan", json=test_plan_data)
    elapsed_time = (time.time() - start_time) * 1000 # in ms

    assert response.status_code == 201
    plan_id = response.json().get("id")
    logger.info(f"Test 1 (POST /plan) OK. ID: {plan_id}. Response Time: {elapsed_time:.2f}ms")
    
    if not plan_id:
        logger.error("Failed to get plan_id from Test 1. Stopping tests.")
        return

    # Test 2: GET /trajectory/{id} - Retrieve the new plan
    start_time = time.time()
    response = client.get(f"/trajectory/{plan_id}")
    elapsed_time = (time.time() - start_time) * 1000 # in ms
    
    assert response.status_code == 200
    retrieved_data = response.json()
    assert retrieved_data['id'] == plan_id
    assert len(retrieved_data['trajectory_points']) > 0
    logger.info(f"Test 2 (GET /trajectory/{plan_id}) OK. Points: {len(retrieved_data['trajectory_points'])}. Response Time: {elapsed_time:.2f}ms")

    # Test 3: GET /trajectories - List all plans
    start_time = time.time()
    response = client.get("/trajectories?limit=1")
    elapsed_time = (time.time() - start_time) * 1000 # in ms

    assert response.status_code == 200
    assert len(response.json()['plans']) == 1
    logger.info(f"Test 3 (GET /trajectories) OK. Response Time: {elapsed_time:.2f}ms")

    # Test 4: Delete the created plan (Basic CRUD operation)
    def db_delete(id_to_delete):
        conn = get_db_connection()
        try:
            conn.execute("DELETE FROM trajectories WHERE id = ?", (id_to_delete,))
            conn.commit()
        finally:
            conn.close()
            
    db_delete(plan_id)
    response = client.get(f"/trajectory/{plan_id}")
    assert response.status_code == 404
    logger.info(f"Test 4 (DELETE) OK. Trajectory successfully deleted.")

    logger.info("--- API Tests Complete ---")


# --- 8. RUNNER BLOCK ---

if __name__ == "__main__":
    # run_tests() # Uncomment to run integrated tests before starting the server
    logger.info("Starting FastAPI server on http://127.0.0.1:8000")
    print("\n--- To run the server, use: uvicorn robot_control_system:app --reload --host 127.0.0.1 --port 8000 --workers 1 --log-config log_config.json (or similar) ---\n")
    # For a simple run in a standard environment (assuming uvicorn is installed):
    # uvicorn.run(app, host="127.0.0.1", port=8000)