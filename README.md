# Campus Network Priority-Based Traffic Management System

**Auto-detecting and fairly prioritizing real-time traffic on campus networks, with live monitoring.**

CS23502 — Networks and Data Communication | 12-Week Mini-Project

---

## Table of Contents

1. [Overview](#overview)
2. [Team](#team)
3. [Anchor Literature](#anchor-literature)
4. [Architecture](#architecture)
5. [Repository Structure](#repository-structure)
6. [Environment Setup](#environment-setup)
7. [How to Run (Full Pipeline)](#how-to-run-full-pipeline)
8. [Testing & Verification History](#testing--verification-history)
9. [Current Results Snapshot](#current-results-snapshot)
10. [Known Issues / Open Items](#known-issues--open-items)
11. [Remaining Work](#remaining-work)
12. [Troubleshooting Log](#troubleshooting-log)
13. [Automated Testing (Table I Generation)](#automated-testing-table-i-generation)
14. [Lane Ownership](#lane-ownership)

---

## Overview

Campus networks typically treat all traffic identically, so latency-sensitive
traffic (video calls, voice) degrades whenever it competes with bulk transfers
(large downloads) on a shared link. This project builds a four-layer pipeline
that automatically detects traffic type from behavior (not manual tagging)
and enforces fairness-aware bandwidth prioritization in software:

1. **Behavioral traffic classification** — infers a flow's tier from packet
   size, timing, and burstiness statistics, not IP/port allow-lists.
2. **Multi-tier fairness-aware prioritization** — Linux HTB queues with a
   guaranteed minimum-bandwidth floor per tier (never full starvation).
3. **Centralized SDN enforcement** — an os-ken (actively-maintained Ryu fork)
   controller over OpenFlow 1.3, installing/updating flow rules dynamically.
4. **Live monitoring dashboard** — a React/Node.js app showing real-time
   per-tier jitter and an ON/OFF toggle for the whole priority engine.

**Novelty framing:** *integration, not invention* — no single paper in our
literature review combines behavior-based classification, dynamic OpenFlow
enforcement, starvation-safe fairness, and a live interactive dashboard
end-to-end. Each individual technique is grounded in a specific published
source (see [Anchor Literature](#anchor-literature)); the contribution is
wiring them into one working pipeline and demonstrating it.

---

## Anchor Literature

Every algorithmic/design claim in this project traces to one of these four
papers. Do not add unsourced technical claims to the report — this has been
enforced strictly throughout the project.

| Ref | Citation | Used for |
|---|---|---|
| 1 | Shahriar et al., arXiv:2403.15975 | Bandwidth-splitting / guaranteed-minimum-rate fairness logic (our Algorithm 2) |
| 2 | Serag et al., *Journal of Network and Systems Management*, Springer Nature, 2025 | ML-based SDN traffic classification pipeline (our Algorithm 1) |
| 3 | Gorkemli et al., IEEE Document 7130421 | Critique of strict-precedence OpenFlow prioritization — motivates the min-rate floor design so lower tiers are never fully starved |
| 4 | Deo et al., *PeerJ Computer Science*, 2024 | Critique of static IP/port-based SDN prioritization — motivates behavioral (not manual-tag) classification |

---

## Architecture

```
                    ┌─────────────────────────────┐
                    │          Mininet             │
                    │   h1, h2, h3 (senders)        │
                    │   h4 (receiver)                │
                    └──────────────┬───────────────┘
                                   │  10 Mbps bottleneck (s1 → h4)
                                   ▼
                    ┌─────────────────────────────┐
                    │      Open vSwitch  s1         │
                    │  OpenFlow 1.3 + 3 HTB queues  │
                    │   Q0 realtime | Q1 besteffort │
                    │        | Q2 bulk               │
                    └──────────────┬───────────────┘
                                   │ REST: /classify /toggle /status
                                   ▼
                    ┌─────────────────────────────┐
                    │   os-ken SDN Controller        │
                    │   priority_controller.py       │
                    │  installs tiered OpenFlow rules│
                    └──────────────▲───────────────┘
                                   │ POST /classify
                    ┌──────────────┴───────────────┐
                    │   integration/bridge.py         │
                    │  sniffs traffic, runs classifier,│
                    │  pushes tier decisions live      │
                    └──────────────▲───────────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │  classifier/traffic_classifier.py│
                    │  packet size / IAT / burstiness  │
                    │  → shallow decision tree          │
                    └───────────────────────────────┘

                    ┌─────────────────────────────┐
                    │  dashboard/backend/server.js    │
                    │  Node/Express + WebSocket,       │
                    │  watches metrics_store.json,     │
                    │  proxies ON/OFF toggle to :8080  │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  dashboard/frontend/src/App.jsx │
                    │  React live jitter chart +       │
                    │  priority-engine ON/OFF toggle   │
                    └─────────────────────────────┘
```

### Tier → Queue mapping (fixed across the whole system)

| Tier | Queue ID | Guaranteed rate | Ceiling (borrowable) | OpenFlow priority |
|---|---|---|---|---|
| Real-time (video) | 0 | 6 Mbps | 10 Mbps | 20 (highest) |
| Best-effort (browsing) | 1 | 2 Mbps | 8 Mbps | 5 (default/catch-all) |
| Bulk (downloads) | 2 | 1 Mbps | 10 Mbps | 20 |

**Design note — do not "fix" this:** `rate` is the guaranteed floor;
`ceil` is borrowable headroom when other tiers aren't using their share. This
is intentional and directly implements the fairness-aware bandwidth-splitting
approach from Shahriar et al. (Ref 1), and specifically avoids the
strict-precedence starvation failure mode critiqued by Gorkemli et al.
(Ref 3). Changing queues to `rate == ceil` (hard caps) would contradict the
project's own novelty claim — if a hard-cap comparison is ever wanted, it
should be a clearly labeled *secondary* experiment, not the primary config.

---

## Repository Structure

```
campus-qos-project/
├── topology/
│   ├── topo.py                  # Mininet topology: h1/h2/h3 → s1 → h4, 10 Mbps bottleneck
│   └── setup_queues.sh           # OVS linux-htb QoS: creates the 3 queues above
├── controller/
│   └── priority_controller.py    # os-ken app, OpenFlow 1.3, REST API (/classify /toggle /status)
├── classifier/
│   ├── traffic_classifier.py     # feature extraction + decision tree + rule-based fallback
│   └── test_data/
│       ├── test_flows.csv        # labelled synthetic training samples (original)
│       ├── model.joblib          # model trained on synthetic samples (superseded)
│       └── model.real.joblib     # model retrained on real captured Mininet traffic (current)
├── integration/
│   └── bridge.py                 # sniffs live traffic → classifier → controller REST
├── dashboard/
│   ├── backend/
│   │   ├── server.js             # Node/Express + WebSocket relay
│   │   ├── package.json
│   │   └── metrics_store.json    # rolling event log written by bridge.py, read by server.js
│   └── frontend/
│       ├── src/App.jsx           # React dashboard UI
│       └── package.json
├── docs/
│   ├── README.md                 # (this file)
│   ├── PROJECT_HANDOFF_REPORT.md # detailed task-by-task handoff / prompt for AI coding agents
│   └── implementation_section.tex# Weeks 5-8 write-up, paste into main.tex
└── requirements.txt
```

---

## Environment Setup

All commands assume **WSL2 Ubuntu**, with the project cloned under your
**Linux home directory** (e.g. `/home/<user>/campus-qos-project`) — **not**
under `/mnt/c/...`. Mininet/OVS behave unreliably on the Windows-mounted
filesystem; this bit us once already (see [Troubleshooting Log](#troubleshooting-log)).

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch python3-pip python3-venv nodejs npm ethtool

# Python virtual environment (holds os-ken, scapy, scikit-learn, etc.)
cd ~/campus-qos-project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **Note:** Mininet itself is a system package, not installed into the
> venv. Scripts that `import mininet` (i.e. `topo.py`) must run under
> **system** Python (`/usr/bin/python3`). Scripts that need `os_ken`,
> `scapy`, `scikit-learn`, `requests` (i.e. the controller and
> `bridge.py`) must run under the **venv** Python
> (`.venv/bin/python3`). Mixing these up produces `ModuleNotFoundError`.

### Passwordless sudo (optional, recommended for repeated testing)

Mininet, OVS, and the topology/bridge scripts need root. To avoid retyping
your password on every run, scope a NOPASSWD rule to exactly these commands
(do **not** grant blanket passwordless root):

```bash
sudo visudo -f /etc/sudoers.d/campus-qos
```
Add (adjust `<user>` and paths to match your actual environment — verify
with `which mn`, `which ovs-vsctl`, `which ovs-ofctl`, `which tc` first):
```
<user> ALL=(ALL) NOPASSWD: /usr/bin/mn, /usr/bin/ovs-vsctl, /usr/bin/ovs-ofctl, /usr/sbin/tc, /usr/bin/python3 /home/<user>/campus-qos-project/topology/topo.py, /home/<user>/campus-qos-project/.venv/bin/python3 /home/<user>/campus-qos-project/integration/bridge.py, /usr/bin/bash /home/<user>/campus-qos-project/topology/setup_queues.sh
```
Verify with `sudo -l`. Remove the file (`sudo rm /etc/sudoers.d/campus-qos`)
once you're done testing for the day — it grants standing privileged access
to those specific commands, so don't leave it in place indefinitely.

### Network offload settings (important for classifier accuracy)

NIC-level packet coalescing (TSO/GSO/GRO) can distort the packet-size and
timing statistics the classifier relies on. Disable these on the relevant
interfaces before running classifier tests:
```bash
ethtool -K <interface> tso off gso off gro off
```
Verify with:
```bash
ethtool -k <interface> | grep -E "tcp-segmentation|generic-segmentation|generic-receive|large-receive"
```

---

## How to Run (Full Pipeline)

Five terminals. Run in this order.

**Terminal 1 — SDN controller:**
```bash
cd ~/campus-qos-project && source .venv/bin/activate
osken-manager controller/priority_controller.py
```
> The correct command is **`osken-manager`** (no second hyphen, no
> `--wsgi-config` flag — earlier drafts of this README had both wrong; see
> [Troubleshooting Log](#troubleshooting-log)). The REST API auto-starts
> because the app declares `_CONTEXTS = {"wsgi": WSGIApplication}`
> internally. Expect an `EventletDeprecationWarning` and a
> `"1 RLock(s) were not greened"` message on startup — both harmless.
> Wait for `Switch 1 connected; base flows installed.` once Terminal 2
> starts.

**Terminal 2 — Mininet topology:**
```bash
sudo /usr/bin/python3 /home/<user>/campus-qos-project/topology/topo.py
```
Drops you into the `mininet>` CLI. Keep this open — traffic generation
happens here.

**Terminal 3 — QoS queues:**
```bash
sudo ovs-vsctl list-ports s1        # confirm actual interface names first
sudo bash /home/<user>/campus-qos-project/topology/setup_queues.sh s1-eth4
sudo ovs-vsctl list qos
sudo ovs-vsctl list queue
```
> **Before every clean test run**, clear any stale flow rules left over
> from manual `ovs-ofctl` testing sessions, then restart the controller so
> only it repopulates the flow table:
> ```bash
> sudo ovs-ofctl -O OpenFlow13 del-flows s1
> ```
> This matters — see the `/status` vs. actual-queue mismatch documented in
> [Known Issues](#known-issues--open-items).

**Terminal 4 — Integration bridge (classifier → controller):**
```bash
cd ~/campus-qos-project && source .venv/bin/activate
sudo /home/<user>/campus-qos-project/.venv/bin/python3 \
  /home/<user>/campus-qos-project/integration/bridge.py \
  --iface s1-eth1,s1-eth2,s1-eth3 \
  --dpid 1 \
  --model classifier/test_data/model.real.joblib
```
> Use `model.real.joblib` (trained on real captured Mininet traffic), not
> the original `model.joblib` (trained on 4 synthetic samples and known to
> misclassify TCP as realtime — see
> [Testing & Verification History](#testing--verification-history)).
> `bridge.py` accepts a comma-separated list of interfaces so all three
> sender-side links can be sniffed at once.

**Terminal 5 — Dashboard:**
```bash
cd ~/campus-qos-project/dashboard/backend
npm install
node server.js
```
```bash
cd ~/campus-qos-project/dashboard/frontend
npm install
npm run build
```
Access from a Windows browser (WSL2's `localhost` forwarding can be
unreliable for some setups) via the WSL IP:
```bash
ip addr show eth0 | grep inet   # find the WSL2 IP, e.g. 172.25.x.x
```
Then browse to `http://<wsl-ip>:4000`.

**Generate test traffic (from the `mininet>` CLI in Terminal 2):**
```
mininet> h4 iperf3 -s -p 5000 &
mininet> h4 iperf3 -s -p 5201 &
mininet> h1 iperf3 -u -c 10.0.0.4 -p 5000 -b 3M -t 30      # realtime-like
mininet> h3 iperf3 -c 10.0.0.4 -p 5201 -t 30                # bulk-like
```

**Toggle the priority engine (from anywhere):**
```bash
curl -X POST http://127.0.0.1:8080/toggle -H "Content-Type: application/json" -d '{"enabled": false}'
```

---

## Testing & Verification History

This section is the actual record of what has been run and confirmed, not
just what was built. Written so any teammate can see exactly what's proven
vs. still assumed.

### ✅ Task 1 — SDN Controller Verification (PASS)

- Fixed a real bug: the controller's static demo rules and
  `classify_and_install()` originally matched on `udp_src`/`tcp_src`, but
  `iperf3` client traffic has the **server's static listening port as the
  destination**, not the source. Changed both to `udp_dst`/`tcp_dst`.
- Confirmed via controller logs: switch connects, then correct tiered
  `FLOW_MOD` rules install automatically — `udp_dst=5000` → queue 0
  (realtime), `tcp_dst=5201` → queue 2 (bulk), default catch-all → queue 1
  (besteffort), all before any traffic even flows.
- Confirmed via traffic: `dump-flows` and `queue-stats` showed packets
  actually routed through the correct queues, matching the numbers from an
  earlier manual-rule sanity test (~7–8 Mbps UDP, near-zero jitter, zero
  HTB drops across all three classes).

### ✅ Task 2 — Classifier Standalone Verification (PASS, then found gaps, then re-verified)

- Confirmed dependencies (`scapy`, `scikit-learn`, `joblib`) import
  correctly in the venv.
- Confirmed `compute_features()` (packet-size/IAT/burstiness math) works.
- Confirmed the rule-based fallback classifier correctly labels synthetic
  realtime/besteffort/bulk feature vectors.
- Trained an initial `DecisionTreeClassifier` on 12 synthetic labelled
  samples (4 per tier), saved/reloaded successfully — **but this only
  proved the training pipeline works, not that it classifies real traffic
  correctly.**
- **When tested against real Mininet traffic, this model failed on TCP**:
  the learned tree relied primarily on `std_iat <= 0.02` → realtime, and
  real captured TCP flows had `std_iat` low enough (~0.004) to fall into
  that bucket, misclassifying bulk TCP as realtime.
- **Root cause + fix:** disabled NIC-level TSO/GSO/GRO offloading (which was
  smoothing out the packet-size variation the classifier needed to see),
  collected 4 real labelled flow samples (2 UDP, 2 TCP) from actual Mininet
  traffic, and retrained. The new model splits on `std_size <= 69.74`
  (packet-size variance) instead of inter-arrival time — UDP's uniform
  packet sizes (`std_size = 0`) vs. TCP's variable sizes (`std_size` in the
  139–316 range for the observed flows) turned out to be a much more
  reliable signal than timing.
- Re-verified: fresh live UDP flows → `realtime`, fresh live TCP flows →
  `bulk`, consistently, through multiple independent test runs.
- Saved as `classifier/test_data/model.real.joblib` — **this is the model
  that should be used going forward**, not the original `model.joblib`.

### ✅ Task 3 — Integration Bridge Verification (PASS, mechanically; caveats below)

- Confirmed `bridge.py` successfully sniffs live traffic across multiple
  interfaces simultaneously (`--iface s1-eth1,s1-eth2,s1-eth3`), runs the
  classifier, and `POST`s decisions to the controller's `/classify`
  endpoint with no manual `ovs-ofctl` involvement.
- Confirmed via `/status` that the bridge's classifications result in
  installed OpenFlow rules.
- Confirmed the metrics pipeline generates real events across all three
  tiers over time (hundreds of events observed, not just one fixed
  category).

### ✅ Task 4 — Dashboard Verification (PASS)

- Fixed missing Node dependencies (`npm install` in
  `dashboard/backend`) — initial run failed with `Cannot find module
  'express'`.
- Confirmed the backend starts and serves the React production build
  (`npm run build` in the frontend, then served via Express's static
  middleware).
- Confirmed `curl http://127.0.0.1:4000` returns `200 OK` with the React
  app's HTML, and `/api/metrics` returns the live metrics store contents.
- Confirmed the dashboard is reachable from a Windows browser via the WSL2
  IP address (`127.0.0.1` from Windows does **not** reach a WSL2-bound
  service reliably in this setup — see
  [Troubleshooting Log](#troubleshooting-log)).
- **Confirmed the ON/OFF toggle actually controls the controller** — this
  is the most important integration result of Task 4: toggling from the
  dashboard changes the controller's `priority_engine_on` state,
  verified via `/status` before and after.

### ⬜ Task 5 — Baseline vs. QoS Matrix (NOT STARTED)

This is the next and final major task. See [Remaining Work](#remaining-work).

---

## Current Results Snapshot

These are real measured numbers from testing so far — useful context, but
**not yet the controlled before/after comparison** Table I needs.

| Traffic | Observed throughput | Notes |
|---|---|---|
| UDP, 8 Mbps offered | ~7.36–8.39 Mbps | Jitter as low as 0.013–0.026 ms, 0% loss |
| UDP, 1 Mbps offered | ~1.05 Mbps | Jitter ~0.022–0.039 ms, 0% loss |
| UDP, 4 Mbps offered | ~4.20 Mbps | Jitter ~0.013 ms, 0% loss |
| TCP, queue 1 (besteffort) | ~3.06–7.66 Mbps | Varies with contention/HTB borrowing |
| TCP, queue 2 (bulk) | ~3.01–9.63 Mbps | Varies with contention/HTB borrowing |
| TCP, queue 2, competing with UDP | ~4.82 Mbps | Direct evidence of queue-based bandwidth management under contention |

HTB class statistics have consistently shown **zero packet drops** across
all three classes during testing.

---

## Known Issues / Open Items

These need resolution before Table I results can be trusted.

### 1. Classifier has no `besteffort` training examples yet

The retrained model (`model.real.joblib`) was trained on only 2 UDP
(realtime) and 2 TCP (bulk) samples — **zero besteffort examples**. The
learned tree is effectively a binary realtime/bulk split
(`std_size <= 69.74`). This means the system currently cannot actually
demonstrate 3-tier behavior end-to-end; besteffort traffic will fall
arbitrarily onto whichever side of that threshold it happens to land on.
**Needs:** a couple of labelled besteffort samples (e.g. moderate-rate,
irregular traffic — a short HTTP request/response pattern rather than a
steady iperf stream) added to the training set before Task 5.

### 2. Possible stale-flow-table inconsistency

One test session observed the controller's `/status` reporting a flow as
`tier: realtime, queue: 0` while the actual installed OVS rule
(`dump-flows`) showed `tcp,tp_dst=5201 actions=set_queue:2`, with traffic
volume confirming queue 2 was the one actually carrying the packets. Most
likely cause: leftover manual `ovs-ofctl` rules from earlier hand-typed
testing sessions still present in the flow table, taking precedence over
what the controller/bridge later tried to install. **Treat OVS
`dump-flows`/`queue-stats` as the authoritative source of truth for actual
packet routing, not the controller's `/status` endpoint, until this is
resolved.** Fix: always run `sudo ovs-ofctl -O OpenFlow13 del-flows s1` and
restart the controller before a clean test run (now reflected in the
[How to Run](#how-to-run-full-pipeline) instructions above).

### 3. Frontend dependency vulnerabilities

`npm install` in `dashboard/frontend` reports 28 vulnerabilities (9 low, 5
moderate, 14 high) from the React/CRA dependency tree. The app compiles and
runs correctly regardless. Treat as a dependency-maintenance item, not a
functional blocker — **do not** run `npm audit fix --force` casually, since
it can introduce breaking changes to `react-scripts`/`recharts` versions
mid-project.

### 4. `main.tex` location

The original Review 1 IEEE-formatted LaTeX paper (`main.tex`/`main.pdf`,
Overleaf-ready) is not currently in this repository. Do not regenerate it
from scratch — that risks citation drift from the anchor papers. Locate the
original (Overleaf project history, team shared drive, or whoever last
downloaded the Review 1 zip) and add it to the repo. Final Table I results
should be merged into the actual `main.tex`, not left only in
`implementation_section.tex`.

---

## Remaining Work

In order:

1. **Add besteffort training samples and retrain the classifier** (see
   Known Issue 1). Confirm all three tiers are actually reachable before
   moving on.
2. **Clear the flow table and confirm a clean baseline** (see Known Issue
   2) before recording any Table I numbers.
3. **Task 5 — Baseline vs. QoS Matrix:** run the same TCP/UDP/ping test
   matrix used for the Week 4 baseline, twice, through the full live
   pipeline (bridge + classifier + controller, not manual `ovs-ofctl`):
   - Once with the priority engine **OFF** (`POST /toggle {"enabled":
     false}`) — reproduces baseline conditions live.
   - Once **ON**, with all three tiers of traffic competing simultaneously.
   - Record throughput, jitter, and loss per tier for both runs.
4. **Locate and integrate `main.tex`** (see Known Issue 4); fill in Table I
   with the Task 5 results.
5. **Final documentation pass:** confirm `docs/README.md` (this file),
   `docs/PROJECT_HANDOFF_REPORT.md`, and `docs/implementation_section.tex`
   are all consistent with the final measured results and final code state.
6. **Final end-to-end demonstration** for review/submission.

---

## Troubleshooting Log

Real issues hit during development, kept here so nobody re-debugs the same
thing twice.

| Symptom | Cause | Fix |
|---|---|---|
| `Command 'os-ken-manager' not found` | Wrong command name assumed in early docs | Use `osken-manager` (no second hyphen) |
| `osken-manager: error: unrecognized arguments: --wsgi-config` | `--wsgi-config` is not a real flag; the WSGI app auto-starts from `_CONTEXTS` in the code | Just run `osken-manager controller/priority_controller.py` |
| `ModuleNotFoundError: No module named 'os_ken'` (or `scapy`, etc.) when running with `sudo` | `sudo python3 ...` uses system Python, not the activated venv | Call the venv interpreter by full path: `sudo /home/<user>/.../.venv/bin/python3 script.py` |
| `ModuleNotFoundError: No module named 'mininet'` inside the venv | Mininet is a system-wide apt package, not installed into the venv | Run `topo.py` with system `/usr/bin/python3`, not the venv's |
| `cp: cannot stat '/mnt/c/Users/.../campus-qos-project'` | Project was actually only ever in the Linux home directory, not the Windows-mounted drive | Confirm location with `ls ~/campus-qos-project` before assuming a copy is needed |
| Sudoers rule silently not matching (still prompts for password) | Typo in the sudoers command path (e.g. trailing stray character), or path pointing at the wrong Python interpreter | `sudo -l` to inspect the exact registered rule; `sudo visudo -f /etc/sudoers.d/campus-qos` to fix — `visudo` validates syntax before saving |
| Dashboard unreachable at `http://127.0.0.1:4000` from a Windows browser | WSL2's `127.0.0.1` from the Windows side doesn't always reach services bound inside WSL2 | Find the WSL2 IP (`ip addr show eth0`) and browse to `http://<wsl-ip>:4000` instead |
| `Error: Cannot find module 'express'` on dashboard backend start | `npm install` was never run in `dashboard/backend` | `cd dashboard/backend && npm install` |
| Classifier misclassifies real TCP traffic as `realtime` | Original model trained on only 4 synthetic samples, learned an unreliable `std_iat` threshold that real TCP flows happened to fall under | Disable NIC offloading (TSO/GSO/GRO), collect real labelled samples, retrain on `std_size` instead — see `model.real.joblib` |
| `/status` shows a different queue than what OVS actually installed | Stale manual `ovs-ofctl` rules left over from earlier hand-typed tests | `sudo ovs-ofctl -O OpenFlow13 del-flows s1` and restart the controller before each clean test |
| `listener bind failed: Address already in use` on `iperf3 -s` | An old `iperf3` server process from a previous test is still running | `pkill -9 iperf3` (or `iperf`) and confirm with `ps aux \| grep iperf` before starting a new server |

---

---

## Automated Testing (Table I Generation)

Manually running iperf3 in the `mininet>` CLI for every trial is slow and
error-prone. `automation/` contains a semi-automated harness that owns
Mininet, cleans stale flows, generates all three traffic tiers
concurrently, toggles the engine ON/OFF, repeats for N trials, and writes
results straight to CSV.

**What's automated:** topology + queue setup, flow-table cleanup between
trials, engine toggling, concurrent multi-tier traffic generation, iperf3
JSON result parsing, OVS flow/queue snapshotting, CSV output, and
before/after averaging. It also bootstraps a trained model automatically
from `classifier/test_data/real_flows.csv` if none exists yet — model
files are gitignored, so a fresh clone never has one committed.

**What's still manual (can't be automated away):** starting the os-ken
controller and the integration bridge in their own terminals first — the
controller is a separate long-running process, and the bridge needs
interfaces that only exist once the experiment's own Mininet topology is
already up.

```bash
# Terminal 1 (leave running):
source .venv/bin/activate
osken-manager controller/priority_controller.py

# Terminal 2 — run the automated harness:
bash automation/run_all.sh 3 15   # 3 trials per engine state, 15s each
```
The script pauses once interfaces exist so you can start the bridge in a
third terminal if you want live classifier decisions during the run:
```bash
sudo /home/<user>/priority-based-network-trafficing/.venv/bin/python3 \
  /home/<user>/priority-based-network-trafficing/integration/bridge.py \
  --iface s1-eth1,s1-eth2,s1-eth3 --dpid 1 \
  --model classifier/test_data/model.real.joblib
```

Results land in `results/table1_results.csv` (raw, per-trial) and
`results/table1_summary.csv` (averaged — this is what goes in the report).
OVS flow/queue snapshots per trial are saved under `results/ovs_snapshots/`
for debugging or as report appendix material. `results/` is gitignored —
don't force-add generated output into the repo.

**Classifier evaluation** (accuracy/precision/recall/F1/confusion matrix,
on held-out data — do not reuse the training CSV):
```bash
source .venv/bin/activate
python3 automation/eval_classifier.py \
  --model classifier/test_data/model.real.joblib \
  --test-data classifier/test_data/holdout_flows.csv   # capture this separately
```

---