#!/usr/bin/env python3
"""
experiment_runner.py
----------------------
Automated end-to-end test/experiment harness for the campus QoS project.

What this DOES automate:
  - Bringing up the Mininet topology and QoS queues
  - Clearing stale OpenFlow rules before each experiment (Known Issue 2)
  - Starting iperf3 servers on h4
  - Toggling the priority engine ON/OFF via the controller's REST API
  - Generating concurrent multi-tier traffic (UDP realtime-like, TCP
    besteffort-like, TCP bulk-like) for a configurable duration
  - Parsing iperf3's JSON output for throughput/jitter/loss per flow
  - Snapshotting `ovs-ofctl dump-flows`/`queue-stats` per trial (for the
    report appendix / debugging)
  - Repeating N trials per engine state and writing everything to a single
    CSV — this is your Table I input, generated directly rather than
    transcribed by hand from terminal output.

What this does NOT automate (must be running already, in separate
terminals, before you run this script):
  1. The os-ken controller: `osken-manager controller/priority_controller.py`
  2. The integration bridge: `bridge.py` sniffing the relevant interfaces
     with your trained model. This script does NOT start the bridge for
     you, because the bridge needs to attach to interfaces that only exist
     once THIS script's Mininet topology is already up — chicken-and-egg.
     See automation/run_all.sh for one way to sequence this with a fixed
     startup delay; adjust timings for your machine.

This script must run as root (needs Mininet/OVS) using the SYSTEM python,
same constraint as topo.py:
    sudo /usr/bin/python3 automation/experiment_runner.py --help

Only the Python standard library is used (no `requests`), specifically so
this script has no dependency on the project's venv — it needs to run
under system Python for Mininet regardless.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "topology"))
from topo import build  # noqa: E402

CONTROLLER_URL = "http://127.0.0.1:8080"

# (host, server_port, protocol, tier_label, client_bandwidth)
# Ports match the controller's static demo rules / your test conventions.
TRAFFIC_PLAN = [
    ("h1", 5000, "udp", "realtime", "3M"),
    ("h2", 5100, "tcp", "besteffort", None),
    ("h3", 5201, "tcp", "bulk", None),
]


def find_bottleneck_iface(net):
    """Finds the OVS-side interface name of the s1<->h4 link (the bottleneck)."""
    s1 = net.get("s1")
    h4 = net.get("h4")
    conns = s1.connectionsTo(h4)
    if not conns:
        raise RuntimeError("No direct link found between s1 and h4 - check topo.py")
    return conns[0][0].name  # intf on the s1 side


def run(cmd, check=True, capture=False):
    print(f"[experiment_runner] $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    if check and result.returncode != 0:
        print(f"[experiment_runner] WARNING: command exited {result.returncode}")
        if capture:
            print(result.stderr)
    return result


def http_post_json(url, payload, timeout=3):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        print(f"[experiment_runner] controller request failed: {e}")
        return None


def http_get_json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        print(f"[experiment_runner] controller request failed: {e}")
        return None


def set_engine(enabled: bool):
    result = http_post_json(f"{CONTROLLER_URL}/toggle", {"enabled": enabled})
    state = "ON" if enabled else "OFF"
    if result and result.get("ok"):
        print(f"[experiment_runner] priority engine set {state}")
    else:
        print(f"[experiment_runner] WARNING: could not confirm engine set {state} - check controller is running")


def clean_flow_table():
    """Addresses Known Issue 2: stale rules from earlier manual testing."""
    run("ovs-ofctl -O OpenFlow13 del-flows s1")
    # Force the controller to reinstall its base/demo flows on the current
    # datapath, since a fresh switch-connect event won't fire again here.
    set_engine(True)
    time.sleep(1)


def run_iperf_trial(net, duration):
    """
    Launches iperf3 servers on h4, then runs all three client flows
    concurrently for `duration` seconds, parsing JSON output from each.
    Returns a list of result dicts (one per flow).
    """
    h4 = net.get("h4")

    # Kill any leftover iperf3 processes from a previous trial.
    h4.cmd("pkill -9 iperf3")
    time.sleep(0.5)

    for _, port, proto, _, _ in TRAFFIC_PLAN:
        udp_flag = "-u" if proto == "udp" else ""
        h4.cmd(f"iperf3 -s {udp_flag} -p {port} -D --logfile /tmp/iperf3_server_{port}.log")
    time.sleep(1)

    # Launch all clients concurrently, each writing JSON to a temp file.
    procs = []
    for host_name, port, proto, tier, bw in TRAFFIC_PLAN:
        host = net.get(host_name)
        outfile = f"/tmp/iperf3_client_{host_name}_{port}.json"
        udp_part = f"-u -b {bw}" if proto == "udp" else ""
        cmd = f"iperf3 -c 10.0.0.4 -p {port} {udp_part} -t {duration} -J > {outfile} 2>&1 &"
        host.cmd(cmd)
        procs.append((host_name, port, proto, tier, outfile))

    # Wait for all clients to finish (duration + margin).
    time.sleep(duration + 3)

    results = []
    for host_name, port, proto, tier, outfile in procs:
        row = {"host": host_name, "port": port, "proto": proto, "tier": tier}
        try:
            with open(outfile) as f:
                data = json.load(f)
            end = data.get("end", {})
            if proto == "udp":
                summary = end.get("sum", {})
                row["throughput_mbps"] = round(summary.get("bits_per_second", 0) / 1e6, 3)
                row["jitter_ms"] = summary.get("jitter_ms")
                row["loss_pct"] = summary.get("lost_percent")
            else:
                summary = end.get("sum_received", {})
                row["throughput_mbps"] = round(summary.get("bits_per_second", 0) / 1e6, 3)
                row["jitter_ms"] = None
                row["loss_pct"] = None
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"[experiment_runner] WARNING: could not parse {outfile}: {e}")
            row.update({"throughput_mbps": None, "jitter_ms": None, "loss_pct": None})
        results.append(row)

    for _, port, _, _, _ in TRAFFIC_PLAN:
        subprocess.run(f"pkill -9 -f 'iperf3.*{port}'", shell=True)

    return results


def snapshot_ovs(trial_label, log_dir):
    for cmd, name in [
        ("ovs-ofctl -O OpenFlow13 dump-flows s1", "dump_flows"),
        ("ovs-ofctl -O OpenFlow13 queue-stats s1", "queue_stats"),
    ]:
        result = run(cmd, check=False, capture=True)
        path = os.path.join(log_dir, f"{trial_label}_{name}.txt")
        with open(path, "w") as f:
            f.write(result.stdout or "")


def main():
    parser = argparse.ArgumentParser(description="Automated QoS experiment runner")
    parser.add_argument("--trials", type=int, default=3, help="trials per engine state")
    parser.add_argument("--duration", type=int, default=15, help="seconds of traffic per trial")
    parser.add_argument("--out", default="results/table1_results.csv", help="output CSV path")
    parser.add_argument("--log-dir", default="results/ovs_snapshots", help="directory for flow/queue snapshots")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("This script needs root (Mininet/OVS). Run with sudo.")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(args.log_dir, exist_ok=True)

    print("[experiment_runner] bringing up topology...")
    net = build()
    net.start()
    time.sleep(2)

    iface = find_bottleneck_iface(net)
    print(f"[experiment_runner] bottleneck interface: {iface}")

    setup_queues_sh = os.path.join(os.path.dirname(__file__), "..", "topology", "setup_queues.sh")
    run(f"bash {setup_queues_sh} {iface}")

    print("[experiment_runner] NOTE: if you need the bridge/classifier live for this "
          "run, start it now in another terminal (interfaces now exist), then press Enter.")
    input("Press Enter once the bridge (if used) is attached and ready...")

    all_rows = []
    for engine_state in [False, True]:
        state_label = "engine_on" if engine_state else "engine_off"
        for trial in range(1, args.trials + 1):
            print(f"\n[experiment_runner] === Trial {trial}/{args.trials}, engine={state_label} ===")
            clean_flow_table()
            set_engine(engine_state)
            time.sleep(1)

            results = run_iperf_trial(net, args.duration)
            snapshot_ovs(f"{state_label}_trial{trial}", args.log_dir)

            for row in results:
                row["engine_state"] = state_label
                row["trial"] = trial
                all_rows.append(row)
                print(f"    {row}")

    fieldnames = ["engine_state", "trial", "host", "port", "proto", "tier",
                  "throughput_mbps", "jitter_ms", "loss_pct"]
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n[experiment_runner] Done. Results written to {args.out}")
    print(f"[experiment_runner] OVS flow/queue snapshots in {args.log_dir}/")

    net.stop()


if __name__ == "__main__":
    main()
