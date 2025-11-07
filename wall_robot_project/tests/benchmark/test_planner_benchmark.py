import time
import robot_control_system as rcs
from robot_control_system import WallPlanRequest, Obstacle


def test_planner_speed_small():
    # Quick benchmark to ensure planner runs fast for small walls
    plan = WallPlanRequest(wall_width=5.0, wall_height=5.0, tool_width=0.1, coverage_margin=0.05, obstacles=[])
    start = time.time()
    path, metrics = rcs.generate_coverage_path(plan)
    elapsed = time.time() - start
    # Expect planner to finish in < 2 seconds for 5x5 with default parameters on CI/dev machines
    assert elapsed < 2.0
    assert metrics.total_points > 0
