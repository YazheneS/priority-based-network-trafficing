# Team Handoff Report — Priority-Based Traffic Management for Campus Networks

**Read this if you're joining the testing effort and haven't been involved
yet.** By the end of this document you should understand what the project
does, what's already proven to work, what's still broken or unverified, and
exactly what you personally need to do next.

For setup commands, full architecture diagrams, and step-by-step run
instructions, see the root [`README.md`](../README.md) — this document
focuses on *status* and *who does what next*, not command syntax.

---

## 1. What This Project Actually Does

**The problem:** on a shared campus network link, a video call and someone's
large file download get treated identically by default. When both compete
for bandwidth, the video call degrades — dropped frames, lag — even though
it's far more sensitive to delay than the download is.

**What we built:** a system that watches network traffic, automatically
figures out what *kind* of traffic each flow is (without anyone manually
labeling it), and gives real-time traffic (like video) a guaranteed minimum
share of bandwidth — while still letting bulk downloads use whatever's left
over. If nothing else is competing, a bulk download can still use the full
link; the moment real-time traffic shows up, it gets first priority.

**How it decides "what kind of traffic":** not by looking at IP addresses or
port numbers (that's brittle and easy to spoof/misconfigure) — by watching
*behavior*. Real-time traffic sends small, steady packets at a steady rate.
Bulk downloads send large packets in bursts. A small machine-learning model
learns to tell these apart from the packets themselves.

**Why this is a real (small) research contribution, not just a class
exercise:** four separate ideas from four published papers are combined
into one working system for the first time — no single one of those papers
does all four things together. That's the whole novelty claim: *integration,
not invention*. Every technical decision in this codebase should trace back
to one of these four papers (cite them, don't introduce unsourced claims):

| Paper | What we took from it |
|---|---|
| Shahriar et al., arXiv:2403.15975 | The math for splitting bandwidth fairly between tiers, with a guaranteed minimum so nothing gets starved to zero |
| Serag et al., Springer JNSM 2025 | The approach of classifying traffic from behavior (packet timing/size) instead of manual rules |
| Gorkemli et al., IEEE Doc. 7130421 | Why strict "always serve tier 1 first, no matter what" designs are bad — they can starve everything else |
| Deo et al., PeerJ CS 2024 | Why static IP/port-based prioritization (the old-fashioned way) doesn't hold up in practice |

---

## 2. The Four Pieces (and where the code lives)

Think of it as a pipeline. Traffic flows through all four stages:

```
1. Mininet + switch          ->  2. Classifier          ->  3. Controller           ->  4. Dashboard
   (emulates the network,         (watches packets,          (decides which             (shows what's
    creates the "queues"           decides: is this            queue each flow            happening,
    that carry priority            realtime, besteffort,        gets, via the              lets you turn
    traffic differently)           or bulk?)                    network protocol           the whole thing
                                                                 OpenFlow)                  on/off)
```

| Stage | Files | What it does in one sentence |
|---|---|---|
| 1. Network | `topology/topo.py`, `topology/setup_queues.sh` | Creates 4 virtual computers and a virtual switch with 3 bandwidth "lanes" (queues), each with a guaranteed minimum but able to borrow spare capacity |
| 2. Classifier | `classifier/traffic_classifier.py` | A small decision-tree model that looks at a flow's packet-size and timing statistics and outputs a label: `realtime`, `besteffort`, or `bulk` |
| 3. Controller | `controller/priority_controller.py`, `integration/bridge.py` | The "brain" — receives the classifier's decision and tells the switch which lane to put that traffic in, live, while traffic is flowing |
| 4. Dashboard | `dashboard/backend/`, `dashboard/frontend/` | A web page showing live per-tier network stats and a switch to turn the whole prioritization system on/off |

**You don't need to understand every line of code to help test this.** You
need to understand: each of these 4 pieces has been individually confirmed
to work, but they haven't all been proven to work *well together, under
realistic conditions, with real measurements* — that's what's left.

---

## 3. What's Already Confirmed Working (don't redo this)

All four pieces have been run live, with real generated traffic, and
individually verified. **Stage 3 (the controller/integration layer) is
complete, including a real bug fix — see Issue 3 below — and does not need
further work in the phases below.**

- **The network/queues (Stage 1):** confirmed the 3 bandwidth lanes exist
  and carry traffic correctly, with zero packet drops observed.
- **The classifier (Stage 2):** confirmed it correctly tells real-time
  (video-like UDP) traffic apart from bulk (large TCP transfer) traffic,
  using real captured network samples — *but only these two categories, see
  Section 4*.
- **The controller (Stage 3) — DONE:** confirmed it automatically installs
  the right traffic-shaping rule when the classifier tells it to, without
  anyone manually typing commands. A real bug was found and fixed here
  (dynamic rules were being silently ignored due to a priority-number
  conflict — see Issue 3). This stage is complete; if you're pulling the
  latest code, the fix is already in place.
- **The dashboard (Stage 4):** confirmed it shows live data and that its
  on/off switch genuinely controls the system, not just the display.

---

## 4. What's Still Broken, Missing, or Unverified

Be aware of these before you start testing — they'll affect your results if
you don't account for them.

### Issue 1 — The classifier can't recognize "besteffort" yet
It's only ever been trained on real-time and bulk examples. Right now it's
effectively a two-category classifier pretending to be three-category. This
is probably the single most important thing to fix before final results are
trustworthy — see Phase 1.

### Issue 2 — Old test rules can linger and cause confusing results
Earlier in the project, rules were sometimes typed in by hand directly
(bypassing the automatic system) to sanity-check things. If those aren't
cleared out before a real test, you can end up "confirming" behavior that's
actually coming from a leftover manual rule, not the real system. **The
automated test script (`automation/run_all.sh`) now clears this
automatically before every trial** — but if you're ever testing manually,
clear it yourself first (command's in the root README's troubleshooting
table).

### Issue 3 — RESOLVED: dynamic rules were being silently ignored
The system uses a priority number to decide which traffic rule "wins" when
more than one could apply. The rule the classifier installs used to have a
*lower* priority number than a leftover default rule covering the same
traffic — meaning the classifier's decision was being silently ignored for
some traffic, even though it looked like it was working. **This is fixed
and confirmed working in the latest code**
(`controller/priority_controller.py`) — no further action needed. Just be
aware this happened, because any test results from before the fix may have
actually been measuring the wrong thing, not genuine classifier-driven
behavior — don't reuse pre-fix numbers in the report.

### Issue 4 — The original project report file is missing
The formal write-up (`main.tex`, a LaTeX document) isn't in this repository.
Someone has it somewhere (Overleaf history, a downloaded zip, a laptop). Do
**not** write a new one from scratch — find the original. A regenerated one
risks losing the careful citation discipline the team has maintained (every
technical claim traced to one of the four anchor papers).

### Issue 5 — Frontend has flagged dependency warnings
`npm install` in the dashboard frontend reports a number of vulnerabilities
in third-party packages. The app works fine regardless — this is a
"someday" cleanup item, not something blocking testing.

---

## 5. Environment Notes (things that will trip you up)

- Everything runs on **WSL2 Ubuntu**. Clone the repo into your **Linux home
  directory** (`~/...`), not the Windows-mounted drive (`/mnt/c/...`) — the
  network emulation tools behave unreliably there.
- There are **two different Python setups** in play: a virtual environment
  (`.venv`) holding this project's Python packages, and the system Python
  which has the network-emulation tool (Mininet) installed system-wide.
  Running a script with the wrong one gives a "module not found" error that
  looks scarier than it is — the root README's troubleshooting table has
  the exact fix.
- The command to start the controller is `osken-manager
  controller/priority_controller.py` — not anything with extra flags or a
  different spelling. (This tripped people up before; it's correct now,
  just flagging it since old notes elsewhere may say otherwise.)
- The dashboard needs to be opened from Windows using the WSL2 machine's IP
  address, not `localhost` — the root README explains how to find it.

Full setup instructions, the complete run sequence, and a troubleshooting
table of every issue hit so far are in the root `README.md`. Read that
before running anything for the first time.

---

## 6. Remaining Work — 3 Phases, Split Across 3 People

The controller/integration layer (Stage 3) is done and needs no further
work — its owner has finished their part. The remaining work below is
split across the other three team members. Use **Person A / Person B /
Person C** as placeholders — assign these to whichever three of you are
picking up the remaining testing, in whatever order makes sense for your
schedules.

| Role | Area |
|---|---|
| **Person A** | Measurement — running experiments, recording results |
| **Person B** | Network & Integration Verification — bandwidth-lane configuration, confirming the controller fix holds up live, final report merge |
| **Person C** | Classifier & Dashboard — retraining the classifier, dashboard verification |

**Do not skip ahead between phases.** Each phase depends on the one before
it being genuinely done, not just attempted.

---

### Phase 1 — Fix the two remaining correctness gaps

**Goal:** by the end of this phase, the classifier recognizes all 3
categories, and someone has independently confirmed the already-fixed
priority bug (Issue 3) actually holds up live. Nothing in Phase 2 should be
trusted until Phase 1 is done.

- **Person C:** Capture real besteffort-style traffic (moderate, irregular
  — e.g. repeated small web requests, not a steady video-like stream),
  label it, add it to `classifier/test_data/real_flows.csv`, and retrain
  the model. Confirm all three tiers are now actually reachable — test each
  one individually and check the predicted label matches what you sent.
- **Person B:** Independently verify the queue configuration is exactly
  what the report will claim: run the queue-inspection commands (see root
  README, "How to Run" section) and confirm the three lanes have the right
  guaranteed-minimum and borrowable-maximum values. Confirm you understand
  *why* they're set up this way (guaranteed floor, not a hard cap — see
  root README's "Architecture" section) so you can explain it if asked.
  Also run one live test confirming the already-fixed priority bug (Issue
  3) genuinely holds: with the classifier and controller both running,
  check via the flow-inspection command that a classifier-driven rule
  actually wins over the leftover default rule. This is a confirmation
  step, not new development — the fix is already in the code.
- **Person A:** Do a first small-scale run of the automated test script
  (`automation/run_all.sh 1 5` — 1 trial, 5 seconds, quick smoke test, not
  the real experiment yet) purely to catch any environment-specific errors
  before the team commits time to the real experiment in Phase 2. Report
  back anything that breaks.

**Phase 1 is done when:** the classifier correctly identifies all three
traffic types on demand, the priority fix is reconfirmed live, and the
automated script runs start-to-finish without errors at least once.

---

### Phase 2 — Run the real experiment and verify the dashboard

**Goal:** produce the actual measured numbers the final report needs.

- **Person A:** Run the full automated experiment
  (`automation/run_all.sh 3 15` or more trials if time allows) — this
  generates all three traffic types competing simultaneously, with the
  prioritization system both off and on, and records throughput/jitter/loss
  for each. This produces `results/table1_summary.csv` — this file *is*
  Table I for the report.
- **Person B:** While Person A's experiment runs, review the saved
  queue/flow snapshots it produces (`results/ovs_snapshots/`) and confirm
  they match what you'd expect given the queue configuration from Phase 1.
  Flag anything that looks inconsistent.
- **Person C:** Separately, capture a handful of fresh traffic samples (not
  used in training) and run `automation/eval_classifier.py` against them to
  get real accuracy/precision/recall/F1 numbers and a confusion matrix for
  the report. Also, during Person A's experiment run, keep the dashboard
  open and confirm it's genuinely showing live data as the experiment
  happens (not just a static page), and that toggling prioritization
  on/off from the dashboard visibly changes the measured numbers you're
  watching.

**Phase 2 is done when:** you have a results CSV with real before/after
numbers for all three traffic tiers, classifier accuracy numbers with a
confusion matrix, and confirmation that the dashboard genuinely tracks the
live system.

---

### Phase 3 — Assemble the final report

**Goal:** everything measured in Phase 2 makes it into the actual written
report, cited correctly, ready to submit.

- **Person A:** Turn the Table I numbers into the report's results table
  (and a chart/graph if the report format calls for one) — the actual
  before/after comparison that proves the prioritization system helps.
- **Person C:** Write up the classifier results section — the accuracy
  numbers, and briefly, the debugging story of how the model was improved
  (it originally relied on the wrong signal and misclassified bulk traffic;
  switching to packet-size variance fixed it — this is worth a paragraph,
  it shows real engineering work, not just "we trained a model and it
  worked").
- **Person B:** Write up the queue-configuration section — what the three
  lanes are, their guaranteed/borrowable values, and reference the
  Shahriar et al. paper for why it's designed this way (guaranteed floor,
  not hard caps). Also locate the original report file (Issue 4), merge
  everyone's sections into it, and do a final pass checking every technical
  claim traces back to one of the four anchor papers.
- **Everyone:** Coordinate one final live demo run of the whole system,
  start to finish, before submission — this is the actual proof-of-concept
  moment, make sure it goes smoothly with everyone present.

**Phase 3 is done when:** the report contains real measured results (not
placeholders), every section has an owner who actually wrote it, citations
are checked, and the team has done one clean final demo run together.

---

## 7. Quick Reference — Who to Ask About What

| Question about... | Ask |
|---|---|
| Network topology, bandwidth queues, HTB configuration, confirming the controller fix | Person B |
| Classifier accuracy, model training, dashboard | Person C |
| Test results, measurements, Table I | Person A |
| "How do I even run this thing" | Root `README.md` first, then whoever's around |

---

## 8. Before You Start — Checklist

- [ ] Read the root `README.md` in full, especially "Environment Setup" and
      "How to Run"
- [ ] Confirm you can `git pull` the latest code
- [ ] Confirm your WSL2 environment has the project cloned under your Linux
      home directory, not `/mnt/c/...`
- [ ] Run `sudo -l` to check if passwordless sudo is already set up for you,
      or set it up per the README if not
- [ ] Do a first test run of whatever your Phase 1 task is *before* trying
      to fix anything — confirm you can reproduce the current behavior
      first, so you know what "fixed" looks like compared to
