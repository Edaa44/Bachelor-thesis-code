#!/usr/bin/env python
"""report.py — consolidates results/*.json (written by run_pipeline.py, one
per instance) into everything needed for an experiments chapter:

  results.csv       raw data, one row per instance
  summary.md         coverage overview + a ready-to-paste markdown table
  scaling_time.png    grounded operators vs. total wall time
  scaling_memory.png  grounded operators vs. peak memory

Run this once, after all array tasks have finished:
    python3 report.py
"""

import csv
import glob
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIELDS = [
    "instance", "n_prop_vars", "n_num_vars", "n_prop_vars_raw", "n_num_vars_raw",
    "n_actions_ungrounded", "n_operators_grounded", "translate_wall_time", "status",
    "search_wall_time", "search_internal_time", "peak_memory_kb",
    "expansions", "plan_length",
]

ALL_INSTANCE_NAMES = (
    [f"drone{i}" for i in range(1, 21)]
    + [f"expedition{i}" for i in range(1, 21)]
)


def load_results(results_dir="results"):
    rows = []
    for path in sorted(glob.glob(f"{results_dir}/*.json")):
        with open(path) as f:
            rows.append(json.load(f))
    return rows


def write_csv(rows, path="results.csv"):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in FIELDS})
    print(f"wrote {path} ({len(rows)} rows)")


def total_wall_time(row):
    t = row.get("translate_wall_time") or 0
    s = row.get("search_wall_time") or 0
    return t + s


def write_summary_md(rows, path="summary.md"):
    n_total = len(ALL_INSTANCE_NAMES)
    found = {r["instance"] for r in rows}
    missing = sorted(set(ALL_INSTANCE_NAMES) - found)

    n_solved = sum(1 for r in rows if r.get("status") == "solved")
    n_unsolvable = sum(1 for r in rows if r.get("status") == "unsolvable")
    n_timeout = sum(1 for r in rows if r.get("status") == "timeout")
    n_other = len(rows) - n_solved - n_unsolvable - n_timeout

    lines = []
    lines.append("# Experiment Results Summary\n")
    lines.append("## Coverage\n")
    lines.append(f"- Total registered instances: {n_total}")
    lines.append(f"- Result files found: {len(rows)}")
    lines.append(f"- Solved: {n_solved} ({100*n_solved/n_total:.1f}% of all instances)")
    lines.append(f"- Unsolvable (provably no solution): {n_unsolvable}")
    lines.append(f"- Timeout: {n_timeout}")
    lines.append(f"- Other / failed: {n_other}")
    if missing:
        lines.append(f"- **Missing result files (job may not have run/finished): {missing}**")
    lines.append("")

    lines.append("## Full Results Table\n")
    header = ("| Instance | Prop.Vars | Num.Vars | Actions (ungr.) | "
               "Operators (grounded) | Translate (s) | Search (s) | "
               "Peak Mem (KB) | Status | Plan Len |")
    sep = "|---" * 9 + "|"
    lines.append(header)
    lines.append(sep)
    for r in sorted(rows, key=lambda r: r["instance"]):
        lines.append(
            f"| {r.get('instance','')} "
            f"| {r.get('n_prop_vars','')} "
            f"| {r.get('n_num_vars','')} "
            f"| {r.get('n_actions_ungrounded','')} "
            f"| {r.get('n_operators_grounded','')} "
            f"| {fmt(r.get('translate_wall_time'))} "
            f"| {fmt(r.get('search_wall_time'))} "
            f"| {r.get('peak_memory_kb','')} "
            f"| {r.get('status','')} "
            f"| {r.get('plan_length','')} |"
        )
    lines.append("")

    solved_rows = [r for r in rows if r.get("status") == "solved" and r.get("n_operators_grounded")]
    if solved_rows:
        biggest = max(solved_rows, key=lambda r: r["n_operators_grounded"])
        smallest = min(solved_rows, key=lambda r: r["n_operators_grounded"])
        lines.append("## Scale Range (solved instances)\n")
        lines.append(f"- Smallest: {smallest['instance']} "
                      f"({smallest['n_operators_grounded']} grounded operators)")
        lines.append(f"- Largest: {biggest['instance']} "
                      f"({biggest['n_operators_grounded']} grounded operators)")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {path}")


def fmt(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) else ""


def make_plots(rows):
    solved = [r for r in rows if r.get("status") == "solved"
              and r.get("n_operators_grounded") and r.get("search_wall_time") is not None]
    if not solved:
        print("no solved instances with complete data -- skipping plots")
        return

    drones = [r for r in solved if r["instance"].startswith("drone")]
    expeditions = [r for r in solved if r["instance"].startswith("expedition")]

    # --- grounded operators vs total wall time ---
    plt.figure(figsize=(7, 5))
    if drones:
        x = [r["n_operators_grounded"] for r in drones]
        y = [total_wall_time(r) for r in drones]
        plt.scatter(x, y, label="drone", marker="o")
    if expeditions:
        x = [r["n_operators_grounded"] for r in expeditions]
        y = [total_wall_time(r) for r in expeditions]
        plt.scatter(x, y, label="expedition", marker="s")
    plt.xlabel("Grounded operators")
    plt.ylabel("Total wall time (s)")
    plt.title("Grounded operator count vs. total wall time")
    plt.legend()
    plt.tight_layout()
    plt.savefig("scaling_time.png", dpi=150)
    plt.close()
    print("wrote scaling_time.png")

    # --- grounded operators vs peak memory ---
    mem_rows = [r for r in solved if r.get("peak_memory_kb")]
    if mem_rows:
        plt.figure(figsize=(7, 5))
        drones_m = [r for r in mem_rows if r["instance"].startswith("drone")]
        expeditions_m = [r for r in mem_rows if r["instance"].startswith("expedition")]
        if drones_m:
            plt.scatter([r["n_operators_grounded"] for r in drones_m],
                        [r["peak_memory_kb"] for r in drones_m],
                        label="drone", marker="o")
        if expeditions_m:
            plt.scatter([r["n_operators_grounded"] for r in expeditions_m],
                        [r["peak_memory_kb"] for r in expeditions_m],
                        label="expedition", marker="s")
        plt.xlabel("Grounded operators")
        plt.ylabel("Peak memory (KB)")
        plt.title("Grounded operator count vs. peak search memory")
        plt.legend()
        plt.tight_layout()
        plt.savefig("scaling_memory.png", dpi=150)
        plt.close()
        print("wrote scaling_memory.png")


def main():
    rows = load_results()
    if not rows:
        print("no results found in results/ -- nothing to report")
        return
    write_csv(rows)
    write_summary_md(rows)
    make_plots(rows)


if __name__ == "__main__":
    main()
