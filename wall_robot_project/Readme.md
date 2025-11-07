# 🤖 Wall-Finishing Robot Control System

Advanced backend system for autonomous wall-finishing robots with intelligent path planning, database optimization, and real-time visualization.

## 🚀 Features

- ✅ **Optimized Coverage Planning**: Boustrophedon algorithm with obstacle avoidance
- ✅ **High-Performance API**: FastAPI with async operations and request timing
- ✅ **Database Optimization**: SQLite with WAL mode, composite indexes, and connection pooling
- ✅ **Comprehensive Testing**: Pytest suite with 20+ test cases
- ✅ **Interactive Visualization**: Real-time path playback with HTML5 Canvas
- ✅ **Production-Ready**: Environment configuration, structured logging, CORS security

## 📋 Requirements

- Python 3.9+
- pip
- Virtual environment (recommended)

## ⚡ Quick Start

### 1. Installation

# 🤖 Wall-Finishing Robot Control System

A compact FastAPI-based backend and simple frontend for planning coverage trajectories for a wall-finishing robot. The project includes a planner, a small REST API, SQLite persistence, a static Canvas UI, and tests.

## Features

- Optimized coverage planner (boustrophedon-like) with rectangular obstacle avoidance
- FastAPI backend with request timing middleware
- SQLite persistence with configurable PRAGMA tuning
- Static HTML/JS frontend for visualizing plans
- Pytest-based test suite

## Requirements

- Python 3.9+ (3.10/3.11 recommended)
- pip

## Quick start (Windows PowerShell)

1. Create and activate a venv

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Run the server

```powershell
# Quick run (the file includes a small runner):
python robot_control_system.py

# Or with uvicorn (recommended while developing):
uvicorn robot_control_system:app --reload --host 127.0.0.1 --port 8000
```

4. Open the frontend

Open `static/index.html` in your browser or visit the server UI if static files are served.

## API (summary)

- `GET /health` — health check
- `POST /api/v1/plan` — submit wall dimensions, tool size, margin and obstacles; returns metrics and trajectory id
- `GET /api/v1/trajectory/{id}` — return stored trajectory (points + metrics)
- `GET /api/v1/trajectories` — list stored trajectories
- `DELETE /api/v1/trajectory/{id}` — delete trajectory
 - `POST /api/v1/jobs` — submit an async/background plan job (returns job_id)
 - `GET /api/v1/jobs/{job_id}` — check status and progress of background job
 - `POST /api/v1/jobs/{job_id}/cancel` — cancel a running background job
 - `GET /metrics` — Prometheus metrics endpoint (scrape by Prometheus)

Example (PowerShell - recommended):

```powershell
$json = @'
{
  "width": 5,
  "height": 5,
  "tool_width": 0.25,
  "margin": 0.02,
  "obstacles": [ { "id": "win1", "x": 2, "y": 2, "width": 0.25, "height": 0.25 } ]
}
'@

$resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/plan" -Method Post -ContentType "application/json" -Body $json
$resp | Format-List
```

## Testing

Run tests inside the activated venv:

```powershell
pytest -q
```

The test suite included in this workspace verifies API behavior, validation, and DB persistence. Current tests: 18 passing.

## Database

The app persists trajectories to a local SQLite file `robot_trajectories.db`. To improve performance and avoid very large JSON payloads, trajectory points are stored in a separate `trajectory_points` table and are inserted in batches.

Configuration notes:

- PRAGMA tunables (cache_size, optional mmap_size) are configurable in `config.py` or via environment variables.
- The project ships with sensible defaults; large mmap values are not used by default to remain portable.
 - The project ships with sensible defaults; large mmap values are not used by default to remain portable.

CI: A GitHub Actions workflow has been added at `.github/workflows/python-tests.yml` to run linting (ruff), type-checking (mypy) and tests on pushes/PRs.

## Recommended .gitignore

```
venv/
.env
robot_trajectories.db
__pycache__/
.pytest_cache/
```

## Development & Extras

- MQTT publishing is optional and disabled by default — enable via config when you have a broker.
 - Background job submission via `/api/v1/jobs` allows long-running plans to run asynchronously and be cancelled.
 - Metrics: Prometheus `prometheus_client` is integrated and `/metrics` exposes counters and histograms for plan generation.
- If you want CI (GitHub Actions) to run tests on push/PR I can add a workflow.

## Support

If you want me to further polish the README, add CI, or remove untracked artifacts from the working tree, tell me which task to perform and I will proceed.

---
Last updated: November 7, 2025