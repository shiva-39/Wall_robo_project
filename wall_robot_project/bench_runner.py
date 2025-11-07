"""Benchmark runner for the wall planner.

Run locally to measure planner throughput and point counts for larger walls.
This script prints a JSON summary to stdout.
"""
import time
import json
from robot_control_system import generate_coverage_path, WallPlanRequest, Obstacle


def run_case(w, h, tool, margin, obstacles):
    plan = WallPlanRequest(
        wall_width=w,
        wall_height=h,
        tool_width=tool,
        coverage_margin=margin,
        obstacles=obstacles
    )
    start = time.perf_counter()
    path, metrics = generate_coverage_path(plan)
    elapsed = time.perf_counter() - start
    return {
        "wall": [w, h],
        "points": metrics.total_points,
        "distance_m": metrics.total_distance_m,
        "time_s": round(elapsed, 3)
    }


def main():
    cases = [
        (5, 5, 0.25, 0.02, [Obstacle(id='o1', x=2, y=2, width=0.25, height=0.25)]),
        (10, 5, 0.1, 0.02, []),
        (20, 10, 0.05, 0.02, [Obstacle(id='o1', x=5, y=2, width=1, height=1)]),
    ]

    results = []
    for w, h, t, m, obs in cases:
        results.append(run_case(w, h, t, m, obs))

    print(json.dumps({"results": results}, indent=2))


if __name__ == '__main__':
    main()
