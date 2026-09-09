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

<img width="942" height="210" alt="Screenshot 2026-09-09 153202" src="https://github.com/user-attachments/assets/fd012cd2-be86-4072-8a34-3a1ca44e3a8e" />


Bandwidth Interpretation

The rate value represents the guaranteed minimum bandwidth for a queue.

The ceil value represents the maximum bandwidth the queue can borrow when
additional bandwidth is available.

Therefore:

Q0 is guaranteed at least 6 Mbps and can borrow bandwidth up to 10 Mbps.
Q1 is guaranteed at least 2 Mbps and can borrow bandwidth up to 8 Mbps.
Q2 is guaranteed at least 1 Mbps and can borrow bandwidth up to 10 Mbps.

The ceiling is therefore not treated as a hard fixed bandwidth allocation.
Unused bandwidth can be utilized by other queues according to the configured
QoS behaviour.
<img width="1007" height="355" alt="Screenshot 2026-09-09 153226" src="https://github.com/user-attachments/assets/05800072-ed1e-4ceb-ad13-b40e01bc0b73" />


2. Issue 3 — OpenFlow Priority Verification

Issue 3 concerned the interaction between classifier-driven OpenFlow rules
and the default catch-all rule.

The expected behaviour is that a specific classifier-driven rule should take
precedence over the leftover/default catch-all rule when both rules can match
the traffic.

The OpenFlow rules were inspected using:

sudo ovs-ofctl -O OpenFlow13 dump-flows s1

The verified traffic-to-queue mapping is:

Traffic Type	Matching Traffic	Queue
Real-time / Video	UDP destination port 5000	Q0
Bulk / Download	TCP destination port 5201	Q2
Best-effort / Browsing	Default/catch-all traffic	Q1

The classifier-specific rules are assigned a higher OpenFlow priority than the
default catch-all rule.

Therefore, when a packet matches a classifier-specific rule, that rule is
selected instead of the lower-priority default rule.

<img width="1242" height="205" alt="Screenshot 2026-09-09 153711" src="https://github.com/user-attachments/assets/8e96d3a6-b87a-446e-a58e-36ab186c309d" />


3. Live Verification

The OpenFlow table and queue behaviour were inspected during live traffic
testing.

The verification confirmed that:

Classifier-driven traffic is mapped to the intended queue.
Specific OpenFlow rules take precedence over the default catch-all rule.
Queue assignment corresponds to the configured traffic class.
The OpenFlow packet and byte counters can be used to confirm that the
expected rules are receiving traffic.

4. Phase 1 Verification Result

The Phase 1 verification assigned to Person B has been completed.

Checklist
 OVS QoS configuration verified
 Q0 guaranteed rate and ceiling verified
 Q1 guaranteed rate and ceiling verified
 Q2 guaranteed rate and ceiling verified
 Difference between guaranteed rate and ceiling verified
 Issue 3 OpenFlow priority behaviour verified
 Classifier-driven rule confirmed to take precedence over the
default catch-all rule
 Live OpenFlow behaviour inspected

Conclusion

The OVS queue configuration and OpenFlow priority behaviour are consistent
with the intended priority-based traffic management design.
