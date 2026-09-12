# Person B — Phase 1 Verification

## Scope

This document records the Phase 1 verification work completed by Person B for the priority-based network traffic management project.

The verification covers:

1. OVS queue configuration
2. Guaranteed minimum and borrowable maximum bandwidth values
3. Issue 3 — OpenFlow rule priority and classifier-driven queue selection

---

## 1. OVS Queue Configuration Verification

The OVS switch was configured with three traffic queues corresponding to the three traffic classes used by the system.

| Queue | Traffic Type            | Guaranteed Rate | Maximum/Ceiling |
| ----- | ------------------------ | ---------------- | ---------------- |
| Q0    | Real-time / Video        | 6 Mbps           | 10 Mbps          |
| Q1    | Best-effort / Browsing   | 2 Mbps           | 8 Mbps           |
| Q2    | Bulk / Downloads         | 1 Mbps           | 10 Mbps          |

The queue configuration was verified using:

```
sudo ovs-vsctl list qos
sudo ovs-vsctl list queue
```

<img width="942" height="210" alt="Screenshot 2026-09-09 153202" src="https://github.com/user-attachments/assets/aa855328-19d9-4413-9929-bec68c3f8e70" />



<img width="1007" height="355" alt="Screenshot 2026-09-09 153226" src="https://github.com/user-attachments/assets/722640cf-49c0-4355-9cb9-068998996afb" />



### Bandwidth Interpretation

The rate value represents the guaranteed minimum bandwidth for a queue.

The ceil value represents the maximum bandwidth the queue can borrow when additional bandwidth is available.

Therefore:

- Q0 is guaranteed at least 6 Mbps and can borrow bandwidth up to 10 Mbps.
- Q1 is guaranteed at least 2 Mbps and can borrow bandwidth up to 8 Mbps.
- Q2 is guaranteed at least 1 Mbps and can borrow bandwidth up to 10 Mbps.

The ceiling is therefore not treated as a hard fixed bandwidth allocation. Unused bandwidth can be utilized by other queues according to the configured QoS behaviour.

---

## 2. Issue 3 — OpenFlow Priority Verification

Issue 3 concerned the interaction between classifier-driven OpenFlow rules and the default catch-all rule.

The expected behaviour is that a specific classifier-driven rule should take precedence over the leftover/default catch-all rule when both rules can match the traffic.

The OpenFlow rules were inspected using:

```
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

The verified traffic-to-queue mapping is:

| Traffic Type            | Matching Traffic             | Queue |
| ------------------------ | ----------------------------- | ----- |
| Real-time / Video         | UDP destination port 5000     | Q0    |
| Bulk / Download           | TCP destination port 5201     | Q2    |
| Best-effort / Browsing    | Default/catch-all traffic     | Q1    |

The classifier-specific rules are assigned a higher OpenFlow priority than the default catch-all rule.

Therefore, when a packet matches a classifier-specific rule, that rule is selected instead of the lower-priority default rule.

<img width="1371" height="236" alt="Screenshot 2026-09-12 231005" src="https://github.com/user-attachments/assets/d409832f-cee6-4e13-b87d-9c17a0ca6e63" />

---

## 3. Live Verification

The OpenFlow table and queue behaviour were inspected during live traffic testing.

`dump-flows` was run while traffic was actively flowing (during a `run_all.sh` experiment run), rather than on an idle switch, so that the per-rule packet/byte counters would reflect real traffic hitting each rule.

```
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

The verification confirmed that:

- Classifier-driven traffic is mapped to the intended queue.
- Specific OpenFlow rules take precedence over the default catch-all rule.
- Queue assignment corresponds to the configured traffic class.
- The OpenFlow packet and byte counters can be used to confirm that the expected rules are receiving traffic.

### Live traffic counter verification

The `dump-flows` output below was captured while `run_all.sh` was actively generating traffic. The `n_packets` and `n_bytes` fields are non-zero on both classifier-driven rules, confirming that live traffic is actually being matched by them (not just that the rules exist).

**Screenshot 1 — `udp,tp_dst=5000` rule with non-zero n_packets / n_bytes**

<img width="1107" height="908" alt="Screenshot 2026-09-12 232500" src="https://github.com/user-attachments/assets/075f8d0f-f622-4737-b54c-825316a99cfb" />

**Screenshot 2 — `tcp,tp_dst=5201` rule with non-zero n_packets / n_bytes**

<img width="998" height="931" alt="Screenshot 2026-09-12 232634" src="https://github.com/user-attachments/assets/3886b227-e547-4261-82b1-2c2f8ba7a405" />

---

## 4. Phase 1 Verification Result

The Phase 1 verification assigned to Person B has been completed.

**Checklist**
- [x] OVS QoS configuration verified
- [x] Q0 guaranteed rate and ceiling verified
- [x] Q1 guaranteed rate and ceiling verified
- [x] Q2 guaranteed rate and ceiling verified
- [x] Difference between guaranteed rate and ceiling verified
- [x] Issue 3 OpenFlow priority behaviour verified
- [x] Classifier-driven rule confirmed to take precedence over the default catch-all rule
- [x] Live OpenFlow behaviour inspected, with non-zero `n_packets`/`n_bytes` confirmed on the `udp,tp_dst=5000` and `tcp,tp_dst=5201` rules during an active `run_all.sh` traffic run

### Conclusion

The OVS queue configuration and OpenFlow priority behaviour are consistent with the intended priority-based traffic management design.
