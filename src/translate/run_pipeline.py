#!/usr/bin/env python
"""run_pipeline.py — translate ONE instance, then search it, all in one process.
Usage: python3 run_pipeline.py drone1"""

import subprocess
import sys
import time
import re
import os

from translate import process_instance, ALL_BETA, instance_name_from_task_path

DOWNWARD_BIN = "/mnt/c/Users/edaer/bachelor/fast-downward/builds/release/bin/downward" #absolute path to downward, in this case wsl path
TIME_LIMIT_S = 1800

def main():
    instance_name = sys.argv[1]  # e.g. "drone1" or "expedition7"

    if instance_name.startswith("drone"):
        domain_path = f"instances/domain_drone.pddl"
    elif instance_name.startswith("expedition"):
        domain_path = f"instances/domain_expedition.pddl"
    else:
        sys.exit(f"unknown instance prefix: {instance_name}")

    task_path = f"instances/problem_{instance_name}.pddl"
    if not os.path.exists(task_path):
        sys.exit(f"task file not found: {task_path}")

    print(f"=== translating {instance_name} ===")
    process_instance(domain_path, task_path)

    sas_path = f"output_classical_{instance_name}.sas"
    if not os.path.exists(sas_path):
        sys.exit(f"translation did not produce {sas_path}")

    print(f"=== searching {instance_name} ===")
    plan_path = f"sas_plan_{instance_name}"
    cmd = [DOWNWARD_BIN, "--search", "astar(blind())",
           "--internal-plan-file", plan_path]

    t0 = time.perf_counter()
    with open(sas_path) as stdin_file:
        result = subprocess.run(
            cmd, stdin=stdin_file, capture_output=True, text=True,
            timeout=TIME_LIMIT_S,
        )
    wall_time = time.perf_counter() - t0

    print(result.stdout)
    print(f"=== done: {instance_name}, wall_time={wall_time:.2f}s ===")

    with open(f"result_{instance_name}.txt", "w") as f:
        f.write(result.stdout)
        f.write(f"\nwall_time={wall_time}\n")

if __name__ == "__main__":
    main()