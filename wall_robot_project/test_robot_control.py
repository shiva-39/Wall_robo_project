"""
Comprehensive test suite for Wall-Finishing Robot Control API.
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
import sqlite3
import os

from robot_control_system import app, get_db_connection, init_db
from config import get_settings

settings = get_settings()

# Test database path
TEST_DB_PATH = "test_robot_trajectories.db"


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Setup test database before tests and cleanup after."""
    # Override settings for testing
    settings.db_path = TEST_DB_PATH
    
    # Initialize test database
    init_db()
    
    yield
    
    # Cleanup: Remove test database
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    for ext in ["-shm", "-wal"]:
        if os.path.exists(TEST_DB_PATH + ext):
            os.remove(TEST_DB_PATH + ext)


@pytest.fixture
def client():
    """Synchronous test client for regular endpoints."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client():
    """Asynchronous test client for async endpoints."""
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac



# --- BASIC FUNCTIONALITY TESTS ---

def test_root_endpoint(client):
    """Test root endpoint returns health status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "version" in data


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["database"] in ["connected", "error"]


# --- PATH PLANNING TESTS ---

def test_create_simple_plan(client):
    """Test creating a basic path plan without obstacles."""
    plan_data = {
        "wall_width": 5.0,
        "wall_height": 5.0,
        "tool_width": 0.1,
        "coverage_margin": 0.05,
        "obstacles": []
    }
    
    response = client.post("/api/v1/plan", json=plan_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "metrics" in data
    assert data["metrics"]["total_points"] > 0


def test_create_plan_with_obstacle(client):
    """Test creating a plan with a single obstacle."""
    plan_data = {
        "wall_width": 5.0,
        "wall_height": 5.0,
        "tool_width": 0.1,
        "coverage_margin": 0.05,
        "obstacles": [
            {
                "id": "window-1",
                "x": 2.0,
                "y": 2.0,
                "width": 0.5,
                "height": 0.5
            }
        ]
    }
    
    response = client.post("/api/v1/plan", json=plan_data)
    assert response.status_code == 201
    data = response.json()
    assert data["metrics"]["total_points"] > 0


def test_create_plan_invalid_dimensions(client):
    """Test validation: negative wall dimensions should fail."""
    plan_data = {
        "wall_width": -5.0,  # Invalid
        "wall_height": 5.0,
        "tool_width": 0.1,
        "obstacles": []
    }
    
    response = client.post("/api/v1/plan", json=plan_data)
    assert response.status_code == 422  # Validation error


def test_create_plan_obstacle_outside_wall(client):
    """Test validation: obstacle outside wall should fail."""
    plan_data = {
        "wall_width": 5.0,
        "wall_height": 5.0,
        "tool_width": 0.1,
        "obstacles": [
            {
                "id": "invalid-obs",
                "x": 4.0,
                "y": 4.0,
                "width": 2.0,  # Exceeds wall width
                "height": 0.5
            }
        ]
    }
    
    response = client.post("/api/v1/plan", json=plan_data)
    assert response.status_code == 422


# --- TRAJECTORY RETRIEVAL TESTS ---

def test_get_trajectory_success(client):
    """Test retrieving an existing trajectory."""
    # First create a plan
    plan_data = {
        "wall_width": 3.0,
        "wall_height": 3.0,
        "tool_width": 0.1,
        "obstacles": []
    }
    create_response = client.post("/api/v1/plan", json=plan_data)
    plan_id = create_response.json()["id"]
    
    # Now retrieve it
    get_response = client.get(f"/api/v1/trajectory/{plan_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == plan_id
    assert len(data["trajectory_points"]) > 0
    assert "metrics" in data


def test_get_trajectory_not_found(client):
    """Test retrieving non-existent trajectory returns 404."""
    response = client.get("/api/v1/trajectory/99999")
    assert response.status_code == 404


# --- LIST TRAJECTORIES TESTS ---

def test_list_trajectories(client):
    """Test listing trajectories with pagination."""
    # Create a couple of plans
    for i in range(3):
        client.post("/api/v1/plan", json={
            "wall_width": 5.0 + i,
            "wall_height": 5.0,
            "tool_width": 0.1,
            "obstacles": []
        })
    
    # List with limit
    response = client.get("/api/v1/trajectories?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["plans"]) <= 2
    assert "total" in data
    assert "has_more" in data


def test_list_trajectories_with_filter(client):
    """Test filtering trajectories by wall width."""
    # Create plans with different widths
    client.post("/api/v1/plan", json={"wall_width": 3.0, "wall_height": 3.0, "tool_width": 0.1, "obstacles": []})
    client.post("/api/v1/plan", json={"wall_width": 7.0, "wall_height": 3.0, "tool_width": 0.1, "obstacles": []})
    
    # Filter for widths >= 5.0
    response = client.get("/api/v1/trajectories?min_width=5.0")
    assert response.status_code == 200
    data = response.json()
    
    # All returned plans should have width >= 5.0
    for plan in data["plans"]:
        assert plan["wall_width"] >= 5.0


# --- DELETE TRAJECTORY TESTS ---

def test_delete_trajectory_success(client):
    """Test deleting an existing trajectory."""
    # Create a plan
    create_response = client.post("/api/v1/plan", json={
        "wall_width": 4.0,
        "wall_height": 4.0,
        "tool_width": 0.1,
        "obstacles": []
    })
    plan_id = create_response.json()["id"]
    
    # Delete it
    delete_response = client.delete(f"/api/v1/trajectory/{plan_id}")
    assert delete_response.status_code == 204
    
    # Verify it's gone
    get_response = client.get(f"/api/v1/trajectory/{plan_id}")
    assert get_response.status_code == 404


def test_delete_trajectory_not_found(client):
    """Test deleting non-existent trajectory returns 404."""
    response = client.delete("/api/v1/trajectory/99999")
    assert response.status_code == 404


# --- PERFORMANCE TESTS ---

def test_response_time_header(client):
    """Test that X-Process-Time header is present."""
    response = client.get("/health")
    assert "x-process-time" in response.headers
    process_time = float(response.headers["x-process-time"])
    assert process_time > 0


@pytest.mark.asyncio
async def test_concurrent_plan_creation(async_client):
    """Test creating multiple plans concurrently."""
    import asyncio
    
    async def create_plan():
        return await async_client.post("/api/v1/plan", json={
            "wall_width": 5.0,
            "wall_height": 5.0,
            "tool_width": 0.1,
            "obstacles": []
        })
    
    # Create 5 plans concurrently
    responses = await asyncio.gather(*[create_plan() for _ in range(5)])
    
    for response in responses:
        assert response.status_code == 201


# --- EDGE CASE TESTS ---

def test_large_wall_dimensions(client):
    """Test handling very large wall dimensions."""
    plan_data = {
        "wall_width": 100.0,
        "wall_height": 100.0,
        "tool_width": 0.5,
        "obstacles": []
    }
    
    response = client.post("/api/v1/plan", json=plan_data)
    assert response.status_code == 201


def test_minimal_wall_dimensions(client):
    """Test handling minimal valid dimensions."""
    plan_data = {
        "wall_width": 0.5,
        "wall_height": 0.5,
        "tool_width": 0.05,
        "coverage_margin": 0.01,
        "obstacles": []
    }
    
    response = client.post("/api/v1/plan", json=plan_data)
    assert response.status_code == 201


def test_multiple_obstacles(client):
    """Test plan with multiple obstacles."""
    plan_data = {
        "wall_width": 10.0,
        "wall_height": 10.0,
        "tool_width": 0.1,
        "obstacles": [
            {"id": "obs1", "x": 2.0, "y": 2.0, "width": 1.0, "height": 1.0},
            {"id": "obs2", "x": 6.0, "y": 6.0, "width": 1.5, "height": 1.5},
            {"id": "obs3", "x": 4.0, "y": 8.0, "width": 0.5, "height": 0.5},
        ]
    }
    
    response = client.post("/api/v1/plan", json=plan_data)
    assert response.status_code == 201


# --- DATABASE TESTS ---

def test_database_persistence():
    """Test that data persists in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check that trajectories table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trajectories'")
    assert cursor.fetchone() is not None
    
    # Check indexes exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = [row[0] for row in cursor.fetchall()]
    assert any('idx_wall_dimensions' in idx for idx in indexes)
    assert any('idx_timestamp' in idx for idx in indexes)
    
    conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
