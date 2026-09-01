#!/usr/bin/env python3
"""
summarize_results.py
-----------------------
Reads the CSV produced by experiment_runner.py and averages across trials,
producing the actual Table I rows (mean +/- std per tier per engine state).

No sudo needed - run under either system or venv python:
    python3 automation/summarize_results.py --in results/table1_results.csv
"""

import argparse
import csv
from collections import defaultdict
from statistics import mean, pstdev


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="infile", default="results/table1_results.csv")
    parser.add_argument("--out", dest="outfile", default="results/table1_summary.csv")
    args = parser.parse_args()

    groups = defaultdict(lambda: {"throughput": [], "jitter": [], "loss": []})

    with open(args.infile, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["engine_state"], row["tier"])
            if row["throughput_mbps"]:
                groups[key]["throughput"].append(float(row["throughput_mbps"]))
            if row["jitter_ms"] and row["jitter_ms"] != "None":
                groups[key]["jitter"].append(float(row["jitter_ms"]))
            if row["loss_pct"] and row["loss_pct"] != "None":
                groups[key]["loss"].append(float(row["loss_pct"]))

    print(f"{'Engine':<10} {'Tier':<12} {'Throughput (Mbps)':<22} {'Jitter (ms)':<18} {'Loss (%)'}")
    print("-" * 85)

    summary_rows = []
    for (engine, tier), vals in sorted(groups.items()):
        tput_str = f"{mean(vals['throughput']):.2f} +/- {pstdev(vals['throughput']):.2f}" if vals["throughput"] else "n/a"
        jit_str = f"{mean(vals['jitter']):.3f} +/- {pstdev(vals['jitter']):.3f}" if len(vals["jitter"]) > 1 else (f"{vals['jitter'][0]:.3f}" if vals["jitter"] else "n/a")
        loss_str = f"{mean(vals['loss']):.2f}" if vals["loss"] else "n/a"
        print(f"{engine:<10} {tier:<12} {tput_str:<22} {jit_str:<18} {loss_str}")
        summary_rows.append({
            "engine_state": engine, "tier": tier,
            "throughput_mean_mbps": round(mean(vals["throughput"]), 3) if vals["throughput"] else "",
            "throughput_std_mbps": round(pstdev(vals["throughput"]), 3) if len(vals["throughput"]) > 1 else "",
            "jitter_mean_ms": round(mean(vals["jitter"]), 4) if vals["jitter"] else "",
            "loss_mean_pct": round(mean(vals["loss"]), 3) if vals["loss"] else "",
            "n_trials": len(vals["throughput"]),
        })

    fieldnames = ["engine_state", "tier", "throughput_mean_mbps", "throughput_std_mbps",
                  "jitter_mean_ms", "loss_mean_pct", "n_trials"]
    with open(args.outfile, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"\nSummary written to {args.outfile}")


if __name__ == "__main__":
    main()
