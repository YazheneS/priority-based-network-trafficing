# OVS Flow/Queue Snapshots — Interpretation Note

These snapshots (`*_dump_flows.txt`, `*_queue_stats.txt`) were captured
automatically by `automation/experiment_runner.py`'s `snapshot_ovs()`
function during each trial of `automation/run_all.sh`.

## Important: counters are cumulative across the run, not per-trial

`run_all.sh` does **not** clear the OpenFlow rules between trials —
`clean_flow_table()` is deliberately disabled in `experiment_runner.py`
because clearing the flow table between trials was breaking connectivity.

As a result, the `n_packets`/`n_bytes` counters in each trial's
`dump_flows.txt` reflect the cumulative total since the rules were first
installed at the start of the run, not that trial's traffic in isolation.
For example, on the bulk rule (`tcp,tp_dst=5201`) across the three
engine-on trials:

```
Trial 1: 644 packets
Trial 2: 707 packets
Trial 3: 770 packets
```

Each number is a running total, not an independent per-trial measurement.

## What this means for the report

**Table I's numbers are unaffected** — those come directly from each
trial's individual `iperf3` output (3 trials x 15s -> mean +/- standard
deviation), not from these OVS counters.

**Suggested report language for referencing these snapshots:**

> "OVS flow and queue snapshots were collected during the trials to
> verify the installation and activity of QoS rules. Since OpenFlow flow
> counters persist across trials, the packet and byte counters are
> cumulative across the experimental run."

Do not describe these as "Trial 1 transferred X packets, Trial 2
transferred Y packets" — they aren't reset counters, so that framing would
misrepresent the data.

## What these snapshots ARE good evidence for

Comparing `engine_off_trial1_dump_flows.txt` against
`engine_on_trial1_dump_flows.txt` shows the actual mechanism at work: the
engine-off rules have no `set_queue` action at all (`actions=NORMAL`),
while the engine-on rules explicitly assign each tier to its queue:

```
udp,tp_dst=5000 -> set_queue:0   (realtime)
tcp,tp_dst=5201 -> set_queue:2   (bulk)
ip              -> set_queue:1   (best-effort)
```

That's real, verified evidence that the QoS rules were installed and
active exactly as designed — use it for that purpose, not for per-trial
throughput figures (use Table I for that).
