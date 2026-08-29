# Month 2 Implementation — Weeks 5 to 8

This covers the four Month 2 deliverables in the 12-week plan, built to plug
into each other end-to-end:

```
Week 5              Week 6                Week 7                 Week 8
SDN Priority   <---  Traffic         --->  Integration      --->  Live
Engine (os-ken)      Classifier            (bridge.py)            Dashboard
```

## Directory map

```
campus-qos-project/
├── topology/
│   ├── topo.py            # Mininet topology (10 Mbps bottleneck, same as baseline)
│   └── setup_queues.sh     # OVS 3-tier HTB queues (min-rate floor per tier)
├── controller/
│   └── priority_controller.py   # os-ken app: installs tiered OpenFlow rules + REST API
├── classifier/
│   └── traffic_classifier.py    # behavioral feature extraction + decision tree
├── integration/
│   └── bridge.py                # wires classifier output -> controller REST
├── dashboard/
│   ├── backend/server.js        # Node/Express + WebSocket metrics relay
│   └── frontend/src/App.jsx     # React live chart + ON/OFF toggle
└── requirements.txt
```

## How the pieces connect

1. **`topo.py`** brings up the Mininet network and points switch `s1` at the
   os-ken controller. **`setup_queues.sh`** then creates 3 OVS HTB queues on
   the bottleneck port — this is the actual bandwidth-splitting mechanism.
2. **`priority_controller.py`** is what makes `s1` an OpenFlow switch under
   programmatic control. On its own (Week 5, tested standalone) it uses a
   couple of static port-based rules just so the tiering can be demoed
   before the real classifier exists.
3. **`traffic_classifier.py`** replaces that static stand-in: it sniffs live
   packets, computes behavioral features per flow (packet size, jitter,
   burstiness — no manual tagging), and predicts a tier.
4. **`bridge.py`** is the seam: it calls the classifier's live stream and,
   for every classified flow, `POST`s to the controller's `/classify`
   endpoint so a real OpenFlow rule gets installed on the fly. It also polls
   `/status` and writes a rolling metrics file for the dashboard.
5. **`server.js`** watches that metrics file and pushes updates over
   WebSocket to **`App.jsx`**, which renders live per-tier jitter and the
   priority-engine ON/OFF toggle. Flipping the toggle calls
   `POST /api/toggle` → the backend proxies to the controller's
   `POST /toggle` → `priority_controller.py` re-installs flows either with
   or without queue differentiation, live.

## Run order (WSL2 Ubuntu)

Open four terminals.

**Terminal 1 — controller:**
```bash
pip install -r ../requirements.txt   # once
os-ken-manager --wsgi-config controller/priority_controller.py controller/priority_controller.py
```

**Terminal 2 — topology (starts switch, connects to controller):**
```bash
sudo python3 topology/topo.py
# once the Mininet CLI prompt appears, in a separate shell run:
sudo bash topology/setup_queues.sh s1-eth4
```

**Terminal 3 — classifier + integration bridge** (replace `s1-eth1` with
whichever switch interface actually carries the traffic you want classified
— check with `sudo ovs-vsctl show` while Mininet is running):
```bash
sudo python3 integration/bridge.py --iface s1-eth1 --dpid 1
```
(Omit `--model` to use the interpretable rule-based fallback classifier
until Week 6's trained model is exported; pass `--model model.joblib` once
you have one — see the training instructions in
`classifier/traffic_classifier.py`.)

**Terminal 4 — dashboard:**
```bash
cd dashboard/backend && npm install && node server.js &
cd ../frontend && npm install && npm start
```
Open the printed `localhost` URL for the frontend dev server.

**Generate test traffic** from the Mininet CLI (terminal 2):
```
mininet> h1 iperf3 -u -c 10.0.0.4 -p 5000 -b 3M -t 60 &   # video-like
mininet> h2 iperf3 -c 10.0.0.4 -p 5100 -t 60 &            # browsing-like
mininet> h3 iperf3 -c 10.0.0.4 -p 5201 -t 60 &            # bulk-like
```

## Citation mapping (for the report / Table I write-up)

| Component | Citation | What it's grounded in |
|---|---|---|
| 3-tier fairness / guaranteed min-rate floor | Shahriar et al., arXiv:2403.15975, Algorithm 2 | bandwidth-splitting logic between tiers |
| Behavioral classification features + shallow decision tree | Serag et al., Springer JNSM 2025 | ML-based SDN traffic classification pipeline |
| Avoiding strict-precedence starvation | IEEE Doc. 7130421 (Gorkemli et al.) | critique of strict-precedence OpenFlow prioritization |
| Controller choice (os-ken over Ryu) | — | Ryu is unmaintained; os-ken is the actively maintained fork |

## What's left before Table I can be finalized

- Re-tune the classifier's decision-tree thresholds against **your own**
  captured samples (the fallback thresholds in `_rule_based_fallback` are
  placeholders pending real training data).
- Run the same TCP/UDP/ping test matrix used for the Week 4 baseline, this
  time with the priority engine **ON**, and record throughput / jitter /
  RTT per tier into Table I next to the existing "before QoS" numbers.
- Confirm final lane ownership (QoS measurement / SDN controller /
  classifier / tc-qdisc) against Monica, Tanishka, Yazhene, and Yamica so
  each of Weeks 5–8 has a clear owner for the write-up.
