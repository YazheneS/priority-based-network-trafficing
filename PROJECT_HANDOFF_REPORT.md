# Project Handoff Report — Priority-Based Traffic Management for Campus Networks

**Purpose of this document:** a complete, self-contained history of what has
been built and tested, and exactly what remains, so this can be pasted as a
single prompt into another AI coding tool (e.g. Antigravity) to finish the
work without losing context. This is a companion to `docs/README.md`, which
covers setup/run instructions in more depth — this document focuses on
status, decisions made, and what's left.

**Last updated:** after Tasks 1–4 completed and verified live; Task 5 not
yet started.

---

## 1. Project Context

**Course:** CS23502 — Networks and Data Communication, 12-week mini-project.

**Title:** "Priority-Based Traffic Management for Campus Networks: Auto-Detecting
and Fairly Prioritizing Real-Time Traffic with Live Monitoring."

**Problem statement:** Campus networks treat all traffic equally, so real-time
traffic (e.g. video calls) degrades when competing with bulk transfers (e.g.
large downloads) on the same link.

**Team (4 members, one shared WSL2 Ubuntu PC for all network experiments):**
- Monica R
- Tanishka K
- Yazhene S — coordinates deliverables, drives content decisions
- Yamica V

**Proposed lane ownership:**
| Lane | Owner | Covers |
|---|---|---|
| QoS measurement | Monica | Baseline + post-QoS test matrix, Table I |
| Linux tc/qdisc | Tanishka | HTB queue setup and tuning |
| SDN/OpenFlow | Yazhene | Controller app, integration bridge |
| Traffic classification | Yamica | Classifier, dashboard |

**Four layered technical contributions (the actual novelty claim):**
1. Behavioral traffic classification — from packet size, timing, burstiness,
   **not** manual tagging.
2. Multi-tier fairness-aware prioritization using Linux `tc`/HTB with a
   guaranteed minimum-bandwidth floor per tier.
3. Centralized SDN control via **os-ken** (the actively maintained Ryu fork —
   Ryu itself is unmaintained) over OpenFlow, on a Mininet virtual network.
4. A live React/Node.js dashboard with an ON/OFF toggle for the priority engine.

**Novelty framing:** "Integration, not invention" — no single existing paper
combines behavior-based classification, dynamic OpenFlow enforcement,
starvation-safe fairness, and a live interactive dashboard in one end-to-end
pipeline.

**Anchor papers (every technical claim/algorithm must trace to one of these):**
| Ref | Citation | Used for |
|---|---|---|
| 1 | Shahriar et al., arXiv:2403.15975 | Bandwidth-splitting / min-rate fairness logic (Algorithm 2) |
| 2 | Serag et al., Springer JNSM 2025 | ML-based SDN traffic classification (Algorithm 1) |
| 3 | Gorkemli et al., IEEE Doc. 7130421 | Critique of strict-precedence OpenFlow prioritization (motivates the min-rate floor design) |
| 4 | Deo et al., PeerJ Computer Science 2024 | Critique of static IP/port-based SDN prioritization (motivates behavioral classification) |

---

## 2. Status Summary (updated)

| Phase | Status |
|---|---|
| Review 1 (Weeks 1-4): problem statement, lit review, architecture, baseline measurements | **Complete and submitted** |
| Month 2 scaffolding (Weeks 5-8): all four components coded | **Complete** |
| Task 1 — SDN controller, live, automatic rule installation | **✅ PASS** |
| Task 2 — Classifier, live traffic, correct tier prediction | **✅ PASS** (after retraining — see Section 5) |
| Task 3 — Integration bridge, classifier → controller, automatic | **✅ PASS** (mechanically; caveats in Section 6) |
| Task 4 — Dashboard, live metrics + working ON/OFF toggle | **✅ PASS** |
| Task 5 — Before/after QoS measurement matrix (Table I) | **⬜ Not started** |

**Bottom line: all four pipeline components are now individually confirmed
working end-to-end with real traffic, through the actual project code — not
manual `ovs-ofctl` stand-ins.** This is a major shift from the previous
version of this report, where only the underlying OVS/HTB mechanism had been
proven and none of the custom code had been run. Two open issues (Section 6)
should be resolved before Task 5 results are trusted for the report.

---

## 3. Review 1 Deliverables Already Produced (do not redo)

- 10-slide PPT (`Review1_Presentation.pptx`)
- Literature review document covering 7 papers with gap synthesis
- Native Draw.io architecture diagram (`architecture.drawio`)
- Full IEEE conference-format LaTeX paper (`main.tex`/`main.pdf`) using IEEEtran
  — **note: this file is not currently in the working repository; see Section
  6, Issue 4. Do not regenerate it from scratch.**
- Baseline measurements on a 10 Mbps virtual link: TCP throughput, UDP
  bandwidth/jitter, ping RTT. UDP jitter under TCP saturation is the key
  "before QoS" evidence point.

**Still outstanding from Review 1:** Table I in `main.tex` has placeholder
metric values — real "before/after QoS" numbers are needed (Task 5).

---

## 4. Architecture and File Structure

See `docs/README.md` for the full architecture diagram and repository
structure — kept there to avoid duplication/drift between the two documents.
Summary of the four components:

- `topology/topo.py` + `topology/setup_queues.sh` — Mininet + 3-tier OVS HTB
  queues (Q0 realtime 6/10 Mbps, Q1 besteffort 2/8 Mbps, Q2 bulk 1/10 Mbps).
- `controller/priority_controller.py` — os-ken app, OpenFlow 1.3, REST API
  (`/classify`, `/toggle`, `/status`).
- `classifier/traffic_classifier.py` — behavioral feature extraction +
  decision tree + rule-based fallback. Current production model is
  `classifier/test_data/model.real.joblib` (see Section 5).
- `integration/bridge.py` — sniffs live traffic on one or more interfaces,
  classifies, pushes decisions to the controller.
- `dashboard/backend/server.js` + `dashboard/frontend/src/App.jsx` —
  Node/Express + WebSocket backend, React frontend, live jitter chart + toggle.

**Design constraint — do not change:** HTB queues use `rate` (guaranteed
floor) with `ceil` (borrowable headroom), not hard caps. This is intentional
per Shahriar et al. (Ref 1) and avoids the starvation failure mode critiqued
in Gorkemli et al. (Ref 3). Confirmed via testing that this produces expected
borrowing behavior (e.g. a bulk flow briefly reaching ~9.6 Mbps when nothing
else was competing, then dropping toward its 1 Mbps floor under contention).

---

## 5. Work Completed Since the Last Version of This Report

### 5.1 Task 1 — SDN Controller (bug found and fixed)

**Bug:** `priority_controller.py`'s static demo rules and
`classify_and_install()` originally matched on `udp_src`/`tcp_src`. This is
wrong for `iperf3` client→server traffic: the client sends from a random
ephemeral port to the server's **fixed listening port**, so the port that
actually identifies the flow is the **destination**, not the source.

**Fix:** changed both the static rules (`_install_demo_static_rules`) and
the dynamic REST-driven path (`classify_and_install`) to match on
`udp_dst`/`tcp_dst` instead.

**Verification:** ran `osken-manager controller/priority_controller.py`
(note: **not** `os-ken-manager --wsgi-config ...` — that command/flag don't
exist; this was a documentation error in earlier drafts, now fixed in the
README) against the live topology. Controller logs confirmed correct
automatic rule installation (`udp_dst=5000` → queue 0, `tcp_dst=5201` →
queue 2, catch-all → queue 1), and `dump-flows`/`queue-stats` confirmed
traffic actually routed through the right queues, matching earlier
manual-rule test numbers.

### 5.2 Task 2 — Classifier (real bug found via live traffic, root-caused, fixed)

**Initial state:** classifier trained on 12 synthetic labelled samples (4 per
tier), round-tripped through save/load correctly. This was previously
reported as "PASS" — but that verification only proved the training
*pipeline* worked, not that the model classified real traffic correctly.

**Bug found when tested against real Mininet traffic:** the model
misclassified real TCP flows as `realtime`. Root cause: `export_text()` on
the tree showed it relied almost entirely on `std_iat <= 0.02` → realtime,
and real captured TCP flows had `std_iat` around 0.004 — comfortably under
that threshold — because NIC-level offloading (TSO/GSO/GRO) was smoothing
out timing variation that would otherwise have been a useful signal.

**Fix:**
1. Disabled TSO/GSO/GRO on the relevant interfaces (`ethtool -K <iface> tso
   off gso off gro off`), confirmed off via `ethtool -k`.
2. Collected 4 real labelled flow samples from actual Mininet traffic (2
   UDP/realtime, 2 TCP/bulk) and retrained.
3. The new model splits on `std_size <= 69.74` (packet-size variance)
   instead of inter-arrival time. UDP's uniform packet sizes (`std_size =
   0`) vs. TCP's variable sizes (observed 139–316 range) turned out to be a
   much more reliable signal.
4. Saved as `classifier/test_data/model.real.joblib`.

**Re-verification:** multiple fresh live UDP flows → `realtime`; multiple
fresh live TCP flows → `bulk`; consistent across independent test runs,
including through the full bridge pipeline (not just offline prediction on
saved feature vectors).

**Known gap (carried into Section 6):** this training set has **zero
besteffort examples** — the model is currently an effective binary
realtime/bulk classifier.

### 5.3 Task 3 — Integration Bridge

Ran `bridge.py` (venv Python, `--model classifier/test_data/model.real.joblib`)
against multiple sender-side interfaces simultaneously
(`--iface s1-eth1,s1-eth2,s1-eth3`), with the controller and topology live.
Confirmed:
- Bridge sniffs and classifies without any manual `ovs-ofctl` involvement.
- Classifications reach the controller via `/classify` and appear in
  `/status`.
- The metrics store (`metrics_store.json`) accumulates real events across
  multiple tiers over time, not one fixed category.

**Known gap (carried into Section 6):** one test session found a
discrepancy between `/status`'s reported tier/queue for a flow and the
actual OVS-installed rule for the same flow.

### 5.4 Task 4 — Dashboard

Fixed a missing-dependency issue (`npm install` had not been run in
`dashboard/backend`, causing `Cannot find module 'express'`). After
installing dependencies and building the React frontend (`npm run build`),
confirmed:
- Backend serves the built frontend and responds `200 OK`.
- `/api/metrics` correctly exposes the live metrics store.
- Dashboard reachable from a Windows browser via the WSL2 IP address (not
  `127.0.0.1` — that doesn't reliably forward from Windows to a WSL2-bound
  service in this setup).
- **The ON/OFF toggle genuinely controls the controller** — verified via
  `/status` before/after clicking it. This is the most important Task 4
  result: the dashboard isn't just a passive display, it actively drives
  the priority engine's live state.

---

## 6. Known Issues — Must Resolve Before Task 5

### Issue 1 — Classifier has no `besteffort` training data
The current production model (`model.real.joblib`) was trained on only 2
UDP (realtime) + 2 TCP (bulk) samples. Zero besteffort examples exist in the
training set, so the learned tree is effectively a binary split and cannot
currently demonstrate genuine 3-tier behavior. **Action:** capture a
besteffort-like traffic pattern (moderate rate, irregular — e.g. repeated
HTTP request/response bursts rather than a steady iperf stream), label it,
and retrain with 3 classes before Task 5.

### Issue 2 — Possible stale OpenFlow rules from earlier manual testing
One test session showed `/status` reporting a flow's tier/queue
inconsistently with what `dump-flows` showed was actually installed and
carrying traffic. Most likely cause: leftover rules from earlier hand-typed
`ovs-ofctl` testing sessions still present in the flow table. **Action:**
before any Task 5 measurement run, clear the flow table
(`sudo ovs-ofctl -O OpenFlow13 del-flows s1`) and restart the controller so
only it repopulates the table — then trust `dump-flows`/`queue-stats` as the
authoritative record of actual packet routing.

### Issue 3 — Frontend dependency vulnerabilities (low priority)
`npm install` in `dashboard/frontend` reports 28 vulnerabilities (9 low, 5
moderate, 14 high). App compiles and runs correctly regardless. Don't run
`npm audit fix --force` casually — risk of breaking `react-scripts`/`recharts`
versions mid-project. Treat as a later cleanup item, not a blocker.

### Issue 4 — `main.tex` not in the working repository
The original Review 1 IEEE paper isn't currently present. Locate the
original file (Overleaf history / team shared drive) rather than
regenerating — a freshly generated paper risks citation drift from the
anchor papers, which this team has been strict about throughout. Final Table
I results should go into the real `main.tex` once it's located, not remain
solely in `implementation_section.tex`.

---

## 7. Remaining Work — Detailed Task List

### Task 5a — Add besteffort classifier training data
Capture and label a besteffort-representative traffic sample, add it to the
training set alongside the existing realtime/bulk samples, retrain, and
re-verify all three tiers are reachable (not just realtime/bulk) before
moving on.

### Task 5b — Clear stale flow-table state
`sudo ovs-ofctl -O OpenFlow13 del-flows s1`, restart the controller, confirm
clean state via `dump-flows` before the first Task 5c measurement.

### Task 5c — Baseline vs. QoS Matrix (the actual Table I data)
With all four components live (controller, classifier w/ 3-class model,
bridge, dashboard) and the flow table clean:
- Run the same TCP throughput / UDP bandwidth+jitter / ping RTT test matrix
  used for the Week 4 baseline, with all three tiers of traffic competing
  simultaneously on the bottleneck link.
- Once with the priority engine **OFF** (`POST /toggle {"enabled": false}`)
  — reproduces baseline conditions live, through the real toggle, not by
  disabling the controller process.
- Once **ON**.
- **Acceptance criteria:** paired before/after numbers per metric per tier,
  ready to drop into Table I. Do not reuse the earlier manual-rule test
  numbers for this comparison — those never included an OFF case and used
  hand-typed rules, not the live pipeline.

### Task 6 — Finalize documentation
- Update `docs/README.md` and `docs/implementation_section.tex` with any
  further deviations discovered during Task 5.
- Locate and integrate `main.tex` (Issue 4); fill Table I with Task 5c
  results.
- Confirm/finalize lane assignments with the actual team.
- Final end-to-end demonstration for submission.

---

## 8. Ready-to-Use Prompt Block for an AI Coding Agent

Everything below this line can be copy-pasted as a single prompt to continue
this work in another tool (Antigravity or similar). It assumes the agent has
access to this repository (`docs/README.md` has full setup/run details) and
a WSL2/Linux environment with Mininet, Open vSwitch, os-ken, Node.js, and
Python already available.

> I'm continuing a university networking mini-project: an SDN-based system
> that auto-classifies campus network traffic into 3 tiers (realtime,
> besteffort, bulk) using behavioral packet features, enforces fairness-aware
> prioritization via os-ken/OpenFlow and Linux HTB queues, and exposes a live
> React/Node.js dashboard with an ON/OFF toggle. Full setup and run
> instructions are in `docs/README.md` — read it first, it has the correct
> commands (note: the controller launch command is `osken-manager
> controller/priority_controller.py`, NOT `os-ken-manager --wsgi-config
> ...`, which doesn't exist).
>
> **Current status: all four pipeline components (controller, classifier,
> integration bridge, dashboard) have been individually verified working
> live, end-to-end, with real Mininet traffic** — this is not a from-scratch
> build. Two issues need fixing before the final measurement task:
>
> 1. The traffic classifier (`classifier/traffic_classifier.py`, current
>    production model `classifier/test_data/model.real.joblib`) was
>    retrained on real captured traffic and correctly distinguishes
>    realtime (UDP) from bulk (TCP) using packet-size variance
>    (`std_size`), but has **zero besteffort training examples** — it's
>    currently a binary classifier in practice. Capture a besteffort-style
>    traffic sample (moderate rate, irregular — e.g. HTTP request/response
>    bursts, not a steady iperf stream), label it, and retrain with all
>    three classes.
> 2. There may be stale OpenFlow rules left in the switch's flow table from
>    earlier manual `ovs-ofctl` testing, causing `/status` (controller's
>    self-reported state) to sometimes disagree with `dump-flows` (actual
>    installed rules). Before any measurement run, clear the flow table
>    (`sudo ovs-ofctl -O OpenFlow13 del-flows s1`) and restart the
>    controller so only it repopulates the table. Treat `dump-flows`/
>    `queue-stats` as ground truth, not `/status`, until this is confirmed
>    resolved.
>
> Once both are fixed, run the final task: a controlled before/after QoS
> measurement. With the full pipeline live (controller + 3-class classifier
> + bridge + dashboard) and the flow table clean, generate all three traffic
> tiers competing simultaneously on the bottleneck link, and record
> throughput/jitter/loss per tier twice — once with the priority engine OFF
> (via `POST /toggle {"enabled": false}`), once ON. These paired numbers are
> the project's final Table I result.
>
> Constraints: do not change the HTB queues from `rate` (guaranteed floor)
> to `rate == ceil` (hard caps) — the borrowing behavior is intentional and
> central to the project's fairness claim (Shahriar et al., arXiv:2403.15975;
> critique of strict precedence in Gorkemli et al., IEEE 7130421). Do not
> regenerate `main.tex` from scratch — locate the original Review 1 paper
> instead and merge final results into it. All algorithmic claims should
> trace to the four anchor papers listed in `docs/README.md`. Report actual
> command output at each step rather than assuming success.
