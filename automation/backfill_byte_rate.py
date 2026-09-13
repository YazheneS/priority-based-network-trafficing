#!/usr/bin/env python3
"""
backfill_byte_rate.py
-----------------------
Adds the new byte_rate feature (see classifier/traffic_classifier.py) to
EXISTING rows in real_flows.csv, without needing to re-capture raw packets
for every sample already collected.

Why this works: real_flows.csv only stores summary stats (mean_size,
mean_iat, etc.), not the raw per-packet sizes/timestamps byte_rate would
normally be computed from. But byte_rate can be closely approximated from
columns that already exist:

    byte_rate ~= (mean_size * WINDOW_SIZE) / (mean_iat * (WINDOW_SIZE - 1))

  - mean_size * WINDOW_SIZE approximates total bytes in the window
  - mean_iat * (WINDOW_SIZE - 1) approximates the window's time span
    (WINDOW_SIZE packets -> WINDOW_SIZE - 1 inter-arrival gaps)

This is an approximation, not a re-derivation of the exact original value -
it assumes the window's true duration is well-represented by mean_iat,
which holds fine for steady traffic but is less exact for very bursty
windows. Good enough to backfill existing rows; NEW captures going forward
get the real, exact byte_rate directly from compute_features() (see
extract_besteffort_features.py, which already calls compute_features() and
will pick up byte_rate automatically once FEATURE_ORDER includes it - no
changes needed there).

IMPORTANT - tested against the real dataset (see commit message / team
notes): this approximation is safe for realtime and besteffort samples,
but breaks down for samples with very small mean_iat (division blows up
toward implausible multi-Gbps values). At the time this was tested, 125 of
221 existing bulk rows produced physically impossible byte_rate values
(>10 Mbps, exceeding this network's actual queue ceiling) this way - do
NOT backfill the bulk class with this script. Let fresh bulk captures
provide real (non-approximated) byte_rate values instead.

Usage:
    python3 automation/backfill_byte_rate.py \\
        --in classifier/test_data/real_flows.csv \\
        --out classifier/test_data/real_flows.csv \\
        --skip-label bulk
    (in-place is fine; it writes to a temp file first and only replaces
    the original after a successful write, so a crash mid-run can't
    corrupt your data)
"""

import argparse
import csv
import os
import tempfile

WINDOW_SIZE = 20  # must match classifier/traffic_classifier.py's WINDOW_SIZE


def backfill(in_path, out_path, skip_labels=None):
    skip_labels = set(skip_labels or [])

    with open(in_path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if "byte_rate" in fieldnames:
        print(f"'{in_path}' already has a byte_rate column - nothing to do.")
        return 0

    # Insert byte_rate right before 'label', matching FEATURE_ORDER's
    # convention of listing features before the label column.
    new_fieldnames = [f for f in fieldnames if f != "label"] + ["byte_rate", "label"]

    skipped = 0
    for row in rows:
        if row["label"] in skip_labels:
            row["byte_rate"] = ""  # left blank - caller must fill from a real recapture
            skipped += 1
            continue
        mean_size = float(row["mean_size"])
        mean_iat = float(row["mean_iat"])
        window_span = mean_iat * (WINDOW_SIZE - 1)
        total_bytes_approx = mean_size * WINDOW_SIZE
        row["byte_rate"] = (total_bytes_approx / window_span) if window_span > 0 else 0.0

    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(out_path)) or ".")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in new_fieldnames})

    os.replace(tmp_path, out_path)
    print(f"Backfilled byte_rate for {len(rows) - skipped} rows -> {out_path}")
    if skipped:
        print(f"Left byte_rate blank for {skipped} row(s) with label(s) {skip_labels} - "
              f"fill these from real captures, not the approximation.")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", dest="out_path", required=True)
    parser.add_argument("--skip-label", dest="skip_labels", action="append", default=[],
                         help="label(s) to leave blank rather than approximate "
                              "(e.g. --skip-label bulk) - repeatable")
    args = parser.parse_args()
    backfill(args.in_path, args.out_path, skip_labels=args.skip_labels)
