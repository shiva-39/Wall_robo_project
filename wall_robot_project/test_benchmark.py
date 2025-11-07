import time
import pytest
from robot_control_system import generate_coverage_path, WallPlanRequest, Obstacle


@pytest.mark.skip(reason="Benchmark test - run manually with RUN_BENCH=1")
def test_large_plan_benchmark():
    # Large wall to measure planner speed (not run by CI)
    plan = WallPlanRequest(
        wall_width=20,
        wall_height=10,
        tool_width=0.05,
        coverage_margin=0.02,
        obstacles=[Obstacle(id='o1', x=5, y=2, width=1, height=1)]
    )

    start = time.perf_counter()
    path, metrics = generate_coverage_path(plan)
    elapsed = time.perf_counter() - start

    print(f"Generated {metrics.total_points} points in {elapsed:.3f}s")
    assert metrics.total_points > 0
