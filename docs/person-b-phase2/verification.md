# Person B — Phase 2 OVS Snapshot Verification

## 1. Objective

The objective of this Phase 2 verification is to review the Open vSwitch (OVS) flow snapshots collected during the experiment and confirm that the engine-off and engine-on configurations match the Phase 1 QoS queue configuration.

The verification specifically checks that:

- Engine-off rules do not contain any `set_queue` action.
- Engine-on rules assign the expected traffic classes to the correct queues.
- UDP traffic with destination port `5000` is assigned to Queue 0.
- Best-effort/default IP traffic is assigned to Queue 1.
- TCP traffic with destination port `5201` is assigned to Queue 2.
- The same expected rule behaviour is maintained across all three trials.

---

## 2. Snapshot Location

The OVS snapshots used for this verification are stored under:

```text
results/ovs_snapshots/
```

The relevant flow snapshot files are:

```text
engine_off_trial1_dump_flows.txt
engine_on_trial1_dump_flows.txt

engine_off_trial2_dump_flows.txt
engine_on_trial2_dump_flows.txt

engine_off_trial3_dump_flows.txt
engine_on_trial3_dump_flows.txt
```

These snapshots were automatically collected by the experiment runner during the three experimental trials. No additional manual OVS snapshot was required for this verification.

---

## 3. Expected Phase 1 Queue Configuration

The expected QoS mapping from the Phase 1 configuration is:

| Traffic Class          | Match                       | Expected Queue |
| ---------------------- | --------------------------- | :------------: |
| Real-time / Video      | UDP destination port `5000` |       Q0       |
| Best-effort / Browsing | Default IP traffic          |       Q1       |
| Bulk / Downloads       | TCP destination port `5201` |       Q2       |

- For the **engine-off** condition, the traffic rules should use normal forwarding without `set_queue`.
- For the **engine-on** condition, the corresponding rules should explicitly assign the traffic to the configured queues.

---

## 4. Trial 1 Verification

### 4.1 Engine-OFF — Trial 1

The following flow rules were observed in the Trial 1 engine-off snapshot:

```text
priority=5,ip actions=NORMAL
priority=20,udp,tp_dst=5000 actions=NORMAL
priority=20,tcp,tp_dst=5201 actions=NORMAL
```

**Observation**

- IP traffic uses `actions=NORMAL`.
- UDP destination port `5000` uses `actions=NORMAL`.
- TCP destination port `5201` uses `actions=NORMAL`.
- No `set_queue` action is present.

Therefore, the Trial 1 engine-off snapshot is consistent with the expected engine-off configuration.

**Evidence — Screenshot 1** (`engine_off_trial1_dump_flows.txt`)
<img width="867" height="291" alt="Screenshot 2026-09-19 181026" src="https://github.com/user-attachments/assets/5be6bfc2-b593-404c-bde9-9bdfd2617fa8" />


### 4.2 Engine-ON — Trial 1

The following queue assignments were observed:

```text
priority=5,ip actions=set_queue:1,NORMAL
priority=20,udp,tp_dst=5000 actions=set_queue:0,NORMAL
priority=20,tcp,tp_dst=5201 actions=set_queue:2,NORMAL
```

**Observation**

- IP/default traffic → `set_queue:1` → Q1
- UDP destination port `5000` → `set_queue:0` → Q0
- TCP destination port `5201` → `set_queue:2` → Q2

The observed queue assignments exactly match the expected Phase 1 configuration.

**Evidence — Screenshot 2** (`engine_on_trial1_dump_flows.txt`)

<img width="930" height="302" alt="Screenshot 2026-09-19 181130" src="https://github.com/user-attachments/assets/2d6ecbef-8c67-4153-876f-01712f7582fb" />


---

## 5. Trial 2 Verification

### 5.1 Engine-OFF — Trial 2

The following flow rules were observed:

```text
priority=5,ip actions=NORMAL
priority=20,udp,tp_dst=5000 actions=NORMAL
priority=20,tcp,tp_dst=5201 actions=NORMAL
```

**Observation**

- IP traffic uses normal forwarding.
- UDP destination port `5000` has no queue assignment.
- TCP destination port `5201` has no queue assignment.
- No `set_queue` action is present.

Therefore, the Trial 2 engine-off configuration is consistent with the expected behaviour.

**Evidence — Screenshot 3** (`engine_off_trial2_dump_flows.txt`)

<img width="921" height="295" alt="Screenshot 2026-09-19 181303" src="https://github.com/user-attachments/assets/673f2523-562e-4e8e-bf87-8401a0e6db3d" />


---

### 5.2 Engine-ON — Trial 2

The following queue assignments were observed:

```text
priority=5,ip actions=set_queue:1,NORMAL
priority=20,udp,tp_dst=5000 actions=set_queue:0,NORMAL
priority=20,tcp,tp_dst=5201 actions=set_queue:2,NORMAL
```

**Observation**

- IP/default traffic → Q1
- UDP destination port `5000` → Q0
- TCP destination port `5201` → Q2

These assignments match the expected Phase 1 QoS configuration.

**Evidence — Screenshot 4** (`engine_on_trial2_dump_flows.txt`)

<img width="932" height="295" alt="Screenshot 2026-09-19 181408" src="https://github.com/user-attachments/assets/49b875e5-30a2-4b19-b794-6f02de73394e" />



---

## 6. Trial 3 Verification

### 6.1 Engine-OFF — Trial 3

The following flow rules were observed:

```text
priority=5,ip actions=NORMAL
priority=20,udp,tp_dst=5000 actions=NORMAL
priority=20,tcp,tp_dst=5201 actions=NORMAL
```

**Observation**

- IP traffic uses normal forwarding.
- UDP destination port `5000` uses normal forwarding.
- TCP destination port `5201` uses normal forwarding.
- No `set_queue` action is present.

Therefore, the Trial 3 engine-off configuration is consistent with the expected engine-off behaviour.

**Evidence — Screenshot 5** (`engine_off_trial3_dump_flows.txt`)

<img width="935" height="298" alt="Screenshot 2026-09-19 181450" src="https://github.com/user-attachments/assets/374795ba-6ec4-4d1e-aeb3-3d819283e416" />


---

### 6.2 Engine-ON — Trial 3

The following queue assignments were observed:

```text
priority=5,ip actions=set_queue:1,NORMAL
priority=20,udp,tp_dst=5000 actions=set_queue:0,NORMAL
priority=20,tcp,tp_dst=5201 actions=set_queue:2,NORMAL
```

**Observation**

- IP/default traffic → Q1
- UDP destination port `5000` → Q0
- TCP destination port `5201` → Q2

The queue assignments match the expected Phase 1 QoS configuration.

**Evidence — Screenshot 6** (`engine_on_trial3_dump_flows.txt`)

<img width="922" height="295" alt="Screenshot 2026-09-19 181539" src="https://github.com/user-attachments/assets/2b74bafe-6ec9-4f1b-ab73-d0f59ecbc04a" />


---

## 7. Trial-Wise Verification Summary

| Trial | Engine State | IP Traffic | UDP dst 5000 | TCP dst 5201 | Result     |
| :---: | :----------: | :--------: | :----------: | :----------: | :--------: |
|   1   |     OFF      |   NORMAL   |    NORMAL    |    NORMAL    | Consistent |
|   1   |      ON      |     Q1     |      Q0      |      Q2      | Consistent |
|   2   |     OFF      |   NORMAL   |    NORMAL    |    NORMAL    | Consistent |
|   2   |      ON      |     Q1     |      Q0      |      Q2      | Consistent |
|   3   |     OFF      |   NORMAL   |    NORMAL    |    NORMAL    | Consistent |
|   3   |      ON      |     Q1     |      Q0      |      Q2      | Consistent |

---

## 8. Counter Interpretation

The `n_packets` and `n_bytes` values in the OVS flow snapshots are cumulative counters across the experimental run.

The flow table was not cleared between trials. Therefore, the packet and byte counters shown in later snapshots represent accumulated activity rather than traffic generated exclusively during that trial.

For this reason, the OVS counters are used in this verification only to confirm that the flow rules are installed and active, not as per-trial throughput measurements.

The per-trial throughput results should be obtained from the individual `iperf3` experiment results rather than from these cumulative OVS counters.

---

## 9. Verification Result

All six OVS flow snapshots were inspected:

- Engine-OFF Trial 1
- Engine-ON Trial 1
- Engine-OFF Trial 2
- Engine-ON Trial 2
- Engine-OFF Trial 3
- Engine-ON Trial 3

The engine-off snapshots consistently showed normal forwarding without `set_queue` actions.

The engine-on snapshots consistently showed the expected QoS assignments:

```text
UDP destination port 5000  → Queue 0
IP/default traffic         → Queue 1
TCP destination port 5201  → Queue 2
```

No inconsistency was identified in the reviewed OVS flow snapshots. Therefore, the observed engine-off and engine-on flow configurations are consistent with the Phase 1 queue configuration.

---


