#!/usr/bin/env python
"""run_pipeline.py — translate ONE instance, then search it, all in one process.
Usage: python3 run_pipeline.py drone1"""

import subprocess
import sys
import json
import time
import re
import os

from translate import process_instance, ALL_BETA, instance_name_from_task_path

#DOWNWARD_BIN = "/mnt/c/Users/edaer/bachelor/fast-downward/builds/release/bin/downward" #absolute path to downward, in this case wsl path
DOWNWARD_BIN = os.environ.get(
    "DOWNWARD_BIN",
    "/infai/erkek0000/downward/builds/release/bin/downward",
)
TIME_LIMIT_S = 1800

os.makedirs("results", exist_ok=True)


def extract(pattern, text, cast=float):
    m = re.search(pattern, text)
    return cast(m.group(1)) if m else None


def write_result(instance_name, result):
    path = f"results/{instance_name}.json"
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"wrote {path}")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 run_pipeline.py <instance_name>")
    instance_name = sys.argv[1]

    if instance_name.startswith("drone"):
        domain_path = "instances/domain_drone.pddl"
    elif instance_name.startswith("expedition"):
        domain_path = "instances/domain_expedition.pddl"
    else:
        sys.exit(f"unknown instance prefix: {instance_name}")

    task_path = f"instances/problem_{instance_name}.pddl"
    if not os.path.exists(task_path):
        sys.exit(f"task file not found: {task_path}")

    print(f"=== translating {instance_name} ===")
    t0 = time.perf_counter()
    translate_stats = process_instance(domain_path, task_path)
    translate_time = time.perf_counter() - t0

    result = {"instance": instance_name, "translate_wall_time": translate_time}
    if translate_stats:
        result.update(translate_stats)

    sas_path = f"output_classical_{instance_name}.sas"
    if not os.path.exists(sas_path):
        result["status"] = "translate_failed"
        write_result(instance_name, result)
        return

    print(f"=== searching {instance_name} ===")
    plan_path = f"sas_plan_{instance_name}"
    cmd = [DOWNWARD_BIN, "--search", "astar(blind())",
           "--internal-plan-file", plan_path]

    t0 = time.perf_counter()
    try:
        with open(sas_path) as stdin_file:
            proc = subprocess.run(
                cmd, stdin=stdin_file, capture_output=True, text=True,
                timeout=TIME_LIMIT_S,
            )
        search_wall_time = time.perf_counter() - t0
        stdout = proc.stdout
    except subprocess.TimeoutExpired:
        result.update({"status": "timeout", "search_wall_time": TIME_LIMIT_S})
        write_result(instance_name, result)
        return

    if "Solution found!" in stdout:
        status = "solved"
    elif "Completely explored state space -- no solution!" in stdout:
        status = "unsolvable"
    else:
        status = "unknown"

    plan_length = None
    if status == "solved" and os.path.exists(plan_path):
        with open(plan_path) as f:
            plan_length = sum(1 for line in f if not line.startswith(";"))

    result.update({
        "status": status,
        "search_wall_time": search_wall_time,
        "search_internal_time": extract(r"Search time:\s*([\d.]+)s", stdout),
        "peak_memory_kb": extract(r"Peak memory:\s*(\d+) KB", stdout, int),
        "expansions": extract(r"Expanded (\d+) state", stdout, int),
        "plan_length": plan_length,
    })

    print(f"=== done: {instance_name}, status={status}, "
          f"search_wall_time={search_wall_time:.2f}s ===")
    write_result(instance_name, result)


if __name__ == "__main__":
    main()