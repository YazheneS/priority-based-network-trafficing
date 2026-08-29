#!/usr/bin/env python3
"""
bridge.py
----------
Week 7 deliverable: Integration.

Connects the Week 6 classifier's live output to the Week 5 controller, so
detected flows automatically get the correct OpenFlow priority rules
installed — with no human in the loop. Also starts the backend metrics
collection service that the Week 8 dashboard will read from.

Data flow:

    traffic_classifier.classify_stream()
            |  (flow_key, tier, features) per re-classified flow
            v
    bridge.on_flow_classified()
            |  POST /classify {dpid, tier, src_ip, dst_ip, src_port, ip_proto}
            v
    controller REST API (priority_controller.py)
            |
            v
    OpenFlow rule installed on s1, mapped to the right OVS queue

    In parallel, bridge.py polls the controller's /status endpoint and
    writes a rolling metrics snapshot to metrics_store.json, which
    dashboard/backend/server.js reads and pushes to the React frontend
    over WebSocket.

Usage (run alongside the controller and topology, as root for sniffing):
    sudo python3 bridge.py --iface s1-eth1 --dpid 1 --model ../classifier/model.joblib
"""

import argparse
import json
import time
import threading

import requests

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "classifier"))
from traffic_classifier import BehavioralClassifier, classify_stream  # noqa: E402

METRICS_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "dashboard", "backend", "metrics_store.json")


def proto_to_ports(feats_key):
    src_ip, dst_ip, src_port, dst_port, proto = feats_key
    return src_ip, dst_ip, src_port, dst_port, proto


def make_flow_handler(controller_url, dpid):
    def on_flow_classified(flow_key, tier, features):
        src_ip, dst_ip, src_port, dst_port, proto = proto_to_ports(flow_key)
        payload = {
            "dpid": dpid,
            "tier": tier,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "src_port": src_port,
            "dst_port": dst_port,
            "ip_proto": proto,
        }
        try:
            resp = requests.post(f"{controller_url}/classify", json=payload, timeout=2)
            status = "ok" if resp.ok else f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            status = f"ERROR: {e}"

        print(f"[bridge] {flow_key} -> tier={tier}  (controller: {status})")
        _append_metrics_event(flow_key, tier, features)

    return on_flow_classified


def _append_metrics_event(flow_key, tier, features):
    """
    Appends a lightweight event to metrics_store.json for the dashboard.
    Kept dead simple (flat JSON file, last N events) since the dashboard
    only needs recent history for its live charts, not a full time-series DB.
    """
    event = {
        "ts": time.time(),
        "flow": str(flow_key),
        "tier": tier,
        "mean_size": features.get("mean_size"),
        "std_size": features.get("std_size"),
        "mean_iat": features.get("mean_iat"),
        "std_iat": features.get("std_iat"),
        "burstiness": features.get("burstiness"),
        "jitter_ms": features.get("jitter_estimate_ms"),
    }
    try:
        if os.path.exists(METRICS_STORE_PATH):
            with open(METRICS_STORE_PATH) as f:
                data = json.load(f)
        else:
            data = {"events": []}
    except (json.JSONDecodeError, FileNotFoundError):
        data = {"events": []}

    data["events"].append(event)
    data["events"] = data["events"][-500:]  # keep it bounded

    os.makedirs(os.path.dirname(METRICS_STORE_PATH), exist_ok=True)
    with open(METRICS_STORE_PATH, "w") as f:
        json.dump(data, f)


def poll_controller_status(controller_url, interval=2):
    """Background thread: periodically pulls controller status into the same store."""
    while True:
        try:
            resp = requests.get(f"{controller_url}/status", timeout=2)
            if resp.ok:
                status = resp.json()
                if os.path.exists(METRICS_STORE_PATH):
                    with open(METRICS_STORE_PATH) as f:
                        data = json.load(f)
                else:
                    data = {"events": []}
                data["controller_status"] = status
                data["last_poll"] = time.time()
                with open(METRICS_STORE_PATH, "w") as f:
                    json.dump(data, f)
        except requests.RequestException as e:
            print(f"[bridge] controller status poll failed: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classifier <-> Controller integration bridge (Week 7)")
    parser.add_argument("--iface", required=True, help="interface to sniff, e.g. s1-eth1")
    parser.add_argument("--dpid", type=int, default=1, help="OpenFlow datapath id of s1")
    parser.add_argument("--model", default=None, help="path to trained classifier model.joblib")
    parser.add_argument("--controller-url", default="http://127.0.0.1:8080", help="os-ken REST base URL")
    args = parser.parse_args()

    clf = BehavioralClassifier(model_path=args.model)
    handler = make_flow_handler(args.controller_url, args.dpid)

    status_thread = threading.Thread(
        target=poll_controller_status, args=(args.controller_url,), daemon=True
    )
    status_thread.start()

    interfaces = [iface.strip() for iface in args.iface.split(",") if iface.strip()]

    print(
        f"[bridge] sniffing {interfaces}, classifying, "
        f"and pushing to {args.controller_url} ..."
    )

    threads = []

    for iface in interfaces:
        t = threading.Thread(
            target=classify_stream,
            args=(iface, clf),
            kwargs={"on_classified": handler},
            daemon=True,
        )
        t.start()
        threads.append(t)
        print(f"[bridge] started classifier on {iface}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[bridge] stopping...")
