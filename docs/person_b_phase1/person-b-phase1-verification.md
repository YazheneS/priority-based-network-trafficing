# Person B — Phase 1 Verification

## Scope

This document records the Phase 1 verification work completed by Person B
for the priority-based network traffic management project.

The verification covers:

1. OVS queue configuration
2. Guaranteed minimum and borrowable maximum bandwidth values
3. Issue 3 — OpenFlow rule priority and classifier-driven queue selection

---

## 1. OVS Queue Configuration Verification

The OVS switch was configured with three traffic queues corresponding to the
three traffic classes used by the system.

| Queue | Traffic Type | Guaranteed Rate | Maximum/Ceiling |
|------|--------------|-----------------|-----------------|
| Q0 | Real-time / Video | 6 Mbps | 10 Mbps |
| Q1 | Best-effort / Browsing | 2 Mbps | 8 Mbps |
| Q2 | Bulk / Downloads | 1 Mbps | 10 Mbps |

The queue configuration was verified using:

```bash
sudo ovs-vsctl list qos
sudo ovs-vsctl list queue
```

Cross-referencing the QoS record's queue UUIDs against each queue's
`min-rate`/`max-rate` confirms the mapping above exactly:

| Queue UUID | min-rate | max-rate | priority | Maps to |
|---|---|---|---|---|
| `8933cf51-d9ad-4267-b6c3-bb2f467de621` | 6 Mbps | 10 Mbps | 1 | Q0 |
| `eff19788-3f0d-4f97-9357-b008605d2bc6` | 2 Mbps | 8 Mbps | 2 | Q1 |
| `c75560c7-ab4e-4794-a644-2f91eb72c71d` | 1 Mbps | 10 Mbps | 3 | Q2 |

![OVS QoS record](https://github.com/user-attachments/assets/fd012cd2-be86-4072-8a34-3a1ca44e3a8e)
![OVS queue details](https://github.com/user-attachments/assets/05800072-ed1e-4ceb-ad13-b40e01bc0b73)

### Bandwidth Interpretation

- The `min-rate` value represents the **guaranteed minimum bandwidth** for a queue.
- The `max-rate` value represents the **maximum bandwidth the queue can borrow**
  when additional bandwidth is available.

Therefore:

- Q0 is guaranteed at least 6 Mbps and can borrow bandwidth up to 10 Mbps.
- Q1 is guaranteed at least 2 Mbps and can borrow bandwidth up to 8 Mbps.
- Q2 is guaranteed at least 1 Mbps and can borrow bandwidth up to 10 Mbps.

The ceiling is therefore not treated as a hard fixed bandwidth allocation.
Unused bandwidth can be utilized by other queues according to the configured
QoS behaviour (this is the guaranteed-floor design referenced in
Shahriar et al., arXiv:2403.15975).

---

## 2. Issue 3 — OpenFlow Priority Verification

Issue 3 concerned the interaction between classifier-driven OpenFlow rules
and the lower-priority rules beneath them.

The expected behaviour is that a specific classifier-driven rule should take
precedence over any lower-priority rule that could also match the same
traffic.

The OpenFlow rules were inspected using:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

The full rule table, in priority order:

| Priority | Match | Action | Role |
|---|---|---|---|
| 100 | `arp` | `NORMAL` | ARP handling, bypasses queueing entirely |
| 20 | `udp,tp_dst=5000` | `set_queue:0,NORMAL` | Real-time -> Q0 |
| 20 | `tcp,tp_dst=5201` | `set_queue:2,NORMAL` | Bulk -> Q2 |
| 5 | `ip` | `set_queue:1,NORMAL` | Best-effort -> Q1 |
| 0 | *(no match, all traffic)* | `NORMAL` | True fallback - no queue assigned |

**Correction from an earlier draft of this table:** best-effort traffic is
**not** routed by a single generic "default/catch-all" rule. It's routed by
a specific `priority=5, ip` rule that matches all IP traffic not already
claimed by the priority-20 real-time/bulk rules, and assigns it to Q1. The
`priority=0` rule is a separate, genuine fallback with **no queue action**
at all - in practice it should rarely or never fire, since non-IP traffic
is already claimed by the priority-100 ARP rule and all IP traffic is
claimed by either a priority-20 rule or the priority-5 rule.

The classifier-specific rules (priority 20) are assigned a higher OpenFlow
priority than the best-effort rule (priority 5), which in turn is higher
than the true fallback (priority 0).

Therefore, when a packet matches a classifier-specific rule, that rule is
selected instead of the lower-priority best-effort or fallback rules.

![OpenFlow rule table](https://github.com/user-attachments/assets/8e96d3a6-b87a-446e-a58e-36ab186c309d)

---

## 3. Live Verification

**Status: rule priorities confirmed via table structure, and now
independently confirmed live with non-zero traffic counters.**

The first `dump-flows` capture (Section 2) was taken shortly after
controller startup (`duration=14.221s` on every rule) with
`n_packets=0, n_bytes=0` across the board - it proved the rule *priorities
and match conditions* were configured as intended, but not that live
traffic actually took the higher-priority path over a lower-priority one.

`dump-flows` was re-run while traffic was actively flowing (during a
`run_all.sh` experiment run), rather than on an idle switch, so that the
per-rule packet/byte counters would reflect real traffic hitting each rule:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

### Live traffic counter verification

The `dump-flows` output below was captured while `run_all.sh` was actively
generating traffic. The `n_packets` and `n_bytes` fields are non-zero on
both classifier-driven rules, confirming that live traffic is actually
being matched by them - not just that the rules exist.

**Screenshot 1 — `udp,tp_dst=5000` rule with non-zero n_packets / n_bytes**

<img width="1107" height="908" alt="Screenshot 2026-09-12 232500" src="https://github.com/user-attachments/assets/075f8d0f-f622-4737-b54c-825316a99cfb" />

**Screenshot 2 — `tcp,tp_dst=5201` rule with non-zero n_packets / n_bytes**

<img width="998" height="931" alt="Screenshot 2026-09-12 232634" src="https://github.com/user-attachments/assets/3886b227-e547-4261-82b1-2c2f8ba7a405" />

Confirmed:

- [x] Classifier-driven traffic is mapped to the intended queue (via rule structure)
- [x] Specific OpenFlow rules are assigned higher priority than the best-effort and fallback rules
- [x] Queue assignment corresponds to the configured traffic class
- [x] Live packet/byte counters confirmed non-zero on the correct rules during real traffic

---

## 4. Phase 1 Verification Result

Phase 1 verification for Person B is complete: queue configuration, rule
priorities, and live-traffic counter confirmation have all been verified.

### Checklist

- [x] OVS QoS configuration verified
- [x] Q0 guaranteed rate and ceiling verified
- [x] Q1 guaranteed rate and ceiling verified
- [x] Q2 guaranteed rate and ceiling verified
- [x] Difference between guaranteed rate and ceiling verified
- [x] Issue 3 OpenFlow priority ordering verified (rule table structure)
- [x] Live OpenFlow packet/byte counters confirmed non-zero on the correct
      rule during real traffic

### Conclusion

The OVS queue configuration and OpenFlow rule priorities are consistent
with the intended priority-based traffic management design, and this has
been confirmed both structurally (rule table inspection) and live (non-zero
traffic counters on the correct rules during an active experiment run).
