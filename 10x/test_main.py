import pytest
from fastapi.testclient import TestClient
from main import app, DATABASE_FILE, init_db
import sqlite3
import os

# Initialize DB before tests run
init_db()

# Use the TestClient for synchronous testing of the FastAPI app
client = TestClient(app)

# --- Fixtures for Setup/Teardown ---

@pytest.fixture(scope="session", autouse=True)
def setup_and_teardown_db():
    """
    Ensures a clean database before and after the test session.
    It connects to the database, wipes the trajectories table, and cleans up the file.
    """
    # 1. Setup: Ensure database is clean before tests run
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trajectories")
    conn.commit()
    conn.close()

    yield # Tests run here

    # 2. Teardown: Clean up the database file after tests
    try:
        os.remove(DATABASE_FILE)
        print(f"\nCleaned up database file: {DATABASE_FILE}")
    except OSError as e:
        print(f"\nError cleaning up database file: {e}")


# --- Test Utility ---

def post_trajectory(client, wall_width=5.0, wall_height=5.0, step_size=0.2):
    """Utility function to post a new trajectory and return the response data."""
    response = client.post(
        "/generate",
        json={
            "wall_width": wall_width,
            "wall_height": wall_height,
            "step_size": step_size,
            "obstacles": [{"x": 2.0, "y": 2.0, "width": 0.25, "height": 0.25}]
        }
    )
    assert response.status_code == 200
    return response.json()

# --- Core API Tests ---

def test_status_endpoint():
    """Test the basic health check endpoint."""
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Wall Robot Control System"}

def test_generate_and_save_trajectory():
    """Test POST /generate endpoint for core functionality and saving."""
    data = post_trajectory(client)
    
    # 1. Check response structure and data validation
    assert "id" in data
    assert data["id"] > 0
    assert data["wall_width"] == 5.0
    assert len(data["trajectory"]) > 0
    assert data["process_time_ms"] > 0

    # 2. Check header logging (custom middleware)
    # Note: TestClient response headers for the last request can be used to check middleware
    response_with_header = client.post(
        "/generate",
        json={
            "wall_width": 5.0,
            "wall_height": 5.0,
            "step_size": 0.2,
            "obstacles": [{"x": 2.0, "y": 2.0, "width": 0.25, "height": 0.25}]
        }
    )
    assert "x-process-time-ms" in response_with_header.headers

def test_get_trajectory_by_id():
    """Test GET /trajectory/{id} endpoint."""
    # First, post a trajectory to get an ID
    post_data = post_trajectory(client, wall_width=6.0, wall_height=4.0)
    trajectory_id = post_data["id"]

    # Now, retrieve it
    response = client.get(f"/trajectory/{trajectory_id}")
    retrieved_data = response.json()

    assert response.status_code == 200
    assert retrieved_data["id"] == trajectory_id
    assert retrieved_data["wall_width"] == 6.0
    # Note: Trajectory length may vary slightly based on geometry
    assert len(retrieved_data["trajectory"]) > 0

def test_get_nonexistent_trajectory():
    """Test retrieving an ID that does not exist."""
    response = client.get("/trajectory/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Trajectory not found."

# --- Advanced Optimization/Monitoring Tests (New) ---

def test_list_recent_trajectories():
    """Test GET /trajectories/recent endpoint, checking for list size and order."""
    # Generate a few more trajectories to ensure data exists
    post_trajectory(client, step_size=0.1) 
    post_trajectory(client, step_size=0.5) 
    last_post = post_trajectory(client, step_size=0.05) 
    max_id = last_post["id"]

    response = client.get("/trajectories/recent")
    recent_list = response.json()
    
    assert response.status_code == 200
    assert isinstance(recent_list, list)
    assert len(recent_list) >= 3 
    
    # Check if the list is ordered correctly (most recent first)
    assert recent_list[0]["id"] == max_id
    assert "wall_size" in recent_list[0] 

def test_get_db_statistics():
    """Test GET /db/stats endpoint for comprehensive server monitoring."""
    # Ensure at least one run exists
    post_trajectory(client) 

    response = client.get("/db/stats")
    stats = response.json()

    assert response.status_code == 200
    assert stats["total_trajectories"] >= 1
    assert stats["avg_process_time_ms"] > 0
    assert stats["fastest_plan_ms"] > 0
    assert stats["slowest_plan_ms"] >= stats["fastest_plan_ms"]
    assert stats["latest_run_id"] is not None