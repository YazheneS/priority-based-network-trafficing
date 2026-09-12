#!/usr/bin/env python3
"""
extract_besteffort_features.py
--------------------------------
Turns a pcap of real captured besteffort-style traffic (short, irregular
HTTP-like request/response bursts - see automation/capture_besteffort.sh)
into labelled feature rows in the same format as
classifier/test_data/real_flows.csv, using the exact same feature math as
the live classifier (classifier/traffic_classifier.compute_features), so
training-time and inference-time features are computed identically.

This does NOT write directly into real_flows.csv. It writes to a separate
review CSV so a human confirms the samples look sane (see Known Issue 1 in
docs/README.md) before merging them into the training set - malformed or
mislabeled samples silently poison the classifier otherwise.

Usage:
    source .venv/bin/activate
    python3 automation/extract_besteffort_features.py \\
        --pcap captures/besteffort_run1.pcap \\
        --host-ip 10.0.0.2 \\
        --out classifier/test_data/besteffort_review.csv

Then, after eyeballing the output:
    tail -n +2 classifier/test_data/besteffort_review.csv \\
        >> classifier/test_data/real_flows.csv
    python3 classifier/traffic_classifier.py \\
        --train classifier/test_data/real_flows.csv \\
        --out classifier/test_data/model.real.joblib
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier"))
from traffic_classifier import compute_features, flow_key, WINDOW_SIZE, BehavioralClassifier  # noqa: E402


def extract_flows(pcap_path, host_ip):
    """
    Reads pcap_path, groups packets into 5-tuple flows touching host_ip,
    and returns a list of feature dicts - one per WINDOW_SIZE-packet window,
    same windowing behaviour as the live classify_stream() path so offline
    training features match what the deployed model will see live.
    """
    from scapy.all import rdpcap, IP, TCP, UDP

    packets = rdpcap(pcap_path)
    windows = defaultdict(lambda: {"sizes": [], "times": []})
    feature_rows = []

    for pkt in packets:
        if IP not in pkt:
            continue
        if pkt[IP].src != host_ip and pkt[IP].dst != host_ip:
            continue

        proto = 6 if TCP in pkt else (17 if UDP in pkt else None)
        if proto is None:
            continue

        if TCP in pkt:
            tcp = pkt[TCP]
            if len(tcp.payload) == 0 and tcp.flags == "A":
                continue  # same ACK-filtering rule as classify_stream()

        sport = pkt[TCP].sport if TCP in pkt else pkt[UDP].sport
        dport = pkt[TCP].dport if TCP in pkt else pkt[UDP].dport
        meta = {"src_ip": pkt[IP].src, "dst_ip": pkt[IP].dst,
                 "src_port": sport, "dst_port": dport, "proto": proto}
        key = flow_key(meta)

        w = windows[key]
        w["sizes"].append(len(pkt))
        w["times"].append(float(pkt.time))

        if len(w["sizes"]) == WINDOW_SIZE:
            feats = compute_features(w["sizes"][-WINDOW_SIZE:], w["times"][-WINDOW_SIZE:])
            if feats:
                feature_rows.append(feats)
            w["sizes"].clear()
            w["times"].clear()

    # Flush any partial final window with at least 2 packets, rather than
    # silently dropping a short capture entirely - besteffort captures are
    # short bursts by design and may not fill a full WINDOW_SIZE window.
    for key, w in windows.items():
        if 2 <= len(w["sizes"]) < WINDOW_SIZE:
            feats = compute_features(w["sizes"], w["times"])
            if feats:
                feature_rows.append(feats)

    return feature_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", required=True, help="path to captured pcap file")
    parser.add_argument("--host-ip", required=True,
                         help="IP of the besteffort sender host (e.g. h2 = 10.0.0.2)")
    parser.add_argument("--out", required=True,
                         help="output review CSV (NOT real_flows.csv directly)")
    parser.add_argument("--label", default="besteffort",
                         help="label to assign (default: besteffort)")
    args = parser.parse_args()

    feature_rows = extract_flows(args.pcap, args.host_ip)

    if not feature_rows:
        print(f"No qualifying flow windows found in {args.pcap} for host {args.host_ip}.")
        print("Check the capture actually contains traffic to/from that host, and that")
        print(f"it has at least 2 packets per flow (WINDOW_SIZE is {WINDOW_SIZE} for a full window,")
        print("but partial windows of >=2 packets are still emitted).")
        sys.exit(1)

    FEATURE_ORDER = BehavioralClassifier.FEATURE_ORDER
    fieldnames = FEATURE_ORDER + ["label"]

    # lineterminator="\n": csv's default is "\r\n" (RFC 4180), which would
    # silently reintroduce CRLF endings into a repo that's otherwise LF-only
    # (see the person-b-phase1 branch cleanup - same class of problem).
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for feats in feature_rows:
            row = {k: feats[k] for k in FEATURE_ORDER}
            row["label"] = args.label
            writer.writerow(row)

    print(f"Extracted {len(feature_rows)} labelled '{args.label}' sample(s) -> {args.out}")
    print("Review these values before appending to real_flows.csv - in particular,")
    print("check mean_size/burstiness look like short irregular HTTP bursts, not an")
    print("accidental steady iperf-like stream (which would just re-learn bulk/realtime).")


if __name__ == "__main__":
    main()
