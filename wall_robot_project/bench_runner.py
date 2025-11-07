"""Benchmark runner for the wall planner.

Run locally to measure planner throughput and point counts for larger walls.
This script prints a JSON summary to stdout.
"""

import time
import json
import tracemalloc
from typing import List
from robot_control_system import generate_coverage_path, WallPlanRequest, Obstacle

from typing import Optional, Any

try:
    import psutil  # type: ignore
    _psutil: Optional[Any] = psutil
except Exception:
    _psutil = None


def capture_peak_memory(func, *args, **kwargs):
    """Run func while measuring peak memory. Use psutil if available, otherwise tracemalloc."""
    if psutil:
        proc = psutil.Process()
        mem_before = proc.memory_info().rss
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        mem_after = proc.memory_info().rss
        # Note: psutil doesn't provide instantaneous peak RSS across the run easily
        # so report delta as approximation.
        peak_rss = max(mem_before, mem_after)
        return result, elapsed, peak_rss
    else:
        tracemalloc.start()
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return result, elapsed, peak


def run_case(w: float, h: float, tool: float, margin: float, obstacles: List[Obstacle]):
    plan = WallPlanRequest(
        wall_width=w,
        wall_height=h,
        tool_width=tool,
        coverage_margin=margin,
        obstacles=obstacles,
    )

    def _run():
        return generate_coverage_path(plan)

    (path, metrics), elapsed, peak_mem = capture_peak_memory(_run)

    return {
        "wall": [w, h],
        "points": metrics.total_points,
        "distance_m": metrics.total_distance_m,
        "time_s": round(elapsed, 3),
        "peak_memory_bytes": int(peak_mem),
    }


def main():
    cases = [
        (5, 5, 0.25, 0.02, [Obstacle(id="o1", x=2, y=2, width=0.25, height=0.25)]),
        (10, 5, 0.1, 0.02, []),
        (20, 10, 0.05, 0.02, [Obstacle(id="o1", x=5, y=2, width=1, height=1)]),
    ]

    results = []
    for w, h, t, m, obs in cases:
        results.append(run_case(w, h, t, m, obs))

    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()
