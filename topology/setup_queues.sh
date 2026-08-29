#!/usr/bin/env bash
#
# setup_queues.sh
# ----------------
# Creates a 3-tier linux-htb QoS profile on the s1-h4 port (the bottleneck
# link, 10 Mbps) using Open vSwitch's native QoS support.
#
# Tiers (grounded in the bandwidth-splitting / min-rate + max-rate logic of
# Shahriar et al., arXiv:2403.15975, Algorithm 2 — "Prioritized Multi-Tenant
# Traffic Engineering for Dynamic QoS Provisioning"):
#
#   Queue 0 - REAL-TIME  (video):     min-rate 6 Mbps, max-rate 10 Mbps
#   Queue 1 - BEST-EFFORT (browsing): min-rate 2 Mbps, max-rate  8 Mbps
#   Queue 2 - BULK (downloads):       min-rate 1 Mbps, max-rate 10 Mbps
#
# The min-rate on Queue 2 is the "starvation-safe" guaranteed floor called
# out in the proposal: bulk traffic is de-prioritized under contention but
# is NEVER driven to zero, which is the specific failure mode of the
# strict-precedence scheme critiqued in Gorkemli et al. (IEEE 7130421).
#
# Run this AFTER `sudo python3 topo.py` has brought s1 up (needs the s1-h4
# interface to exist). Re-run any time to reset the QoS config.
#
# Usage:
#   sudo bash setup_queues.sh s1-eth4
#
set -euo pipefail

IFACE="${1:-s1-eth4}"
LINK_MBPS=10000000   # 10 Mbps in bits/sec, OVS QoS values are in bps

echo "[*] Clearing any existing QoS config on $IFACE"
sudo ovs-vsctl -- clear port "$IFACE" qos

echo "[*] Creating linux-htb QoS with 3 queues on $IFACE"
sudo ovs-vsctl -- set port "$IFACE" qos=@newqos \
  -- --id=@newqos create qos type=linux-htb \
       other-config:max-rate=$LINK_MBPS \
       queues:0=@q_realtime \
       queues:1=@q_besteffort \
       queues:2=@q_bulk \
  -- --id=@q_realtime create queue \
       other-config:min-rate=6000000 \
       other-config:max-rate=10000000 \
       other-config:priority=1 \
  -- --id=@q_besteffort create queue \
       other-config:min-rate=2000000 \
       other-config:max-rate=8000000 \
       other-config:priority=2 \
  -- --id=@q_bulk create queue \
       other-config:min-rate=1000000 \
       other-config:max-rate=10000000 \
       other-config:priority=3

echo "[*] Done. Verify with:"
echo "    ovs-vsctl list qos"
echo "    ovs-vsctl list queue"
