#!/usr/bin/env python3
"""
topo.py
--------
Mininet topology for "Priority-Based Traffic Management for Campus Networks".

Layout:

    h1 (video sender)  ---\\
    h2 (browsing sender) ---- s1 (OVS, OpenFlow 1.3) ----[10 Mbps bottleneck]---- h4 (all receivers' side)
    h3 (bulk sender)     ---/

We keep the SAME bottleneck (10 Mbps, matching the Week 4 baseline measurements
already captured on the 10 Mbps virtual link) so Month 2 "after QoS" results are
directly comparable to the Month 1 "before QoS" numbers in Table I.

s1 is left as an OVSSwitch in "secure" mode pointed at a REMOTE controller
(the os-ken app in controller/priority_controller.py) rather than using
Mininet's own reference controller — this is required for the controller
to install the tiered OpenFlow rules described in Week 5.

Usage (inside WSL2 Ubuntu, os-ken controller already running separately):
    sudo python3 topo.py
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

CONTROLLER_IP = "127.0.0.1"
CONTROLLER_PORT = 6653          # os-ken / OpenFlow default
BOTTLENECK_MBPS = 10            # matches Week 4 baseline link speed


def build():
    net = Mininet(controller=RemoteController, switch=OVSSwitch, link=TCLink, autoSetMacs=True)

    info("*** Adding remote os-ken controller\n")
    c0 = net.addController(
        "c0", controller=RemoteController, ip=CONTROLLER_IP, port=CONTROLLER_PORT
    )

    info("*** Adding switch\n")
    s1 = net.addSwitch("s1", protocols="OpenFlow13")

    info("*** Adding hosts (one per traffic tier, sender side)\n")
    h1 = net.addHost("h1", ip="10.0.0.1/24")   # real-time / video sender
    h2 = net.addHost("h2", ip="10.0.0.2/24")   # best-effort / browsing sender
    h3 = net.addHost("h3", ip="10.0.0.3/24")   # bulk sender (background download)
    h4 = net.addHost("h4", ip="10.0.0.4/24")   # shared receiver (dashboard server also runs here)

    info("*** Creating links\n")
    # Sender-side links: generous, not the bottleneck.
    net.addLink(h1, s1, bw=100)
    net.addLink(h2, s1, bw=100)
    net.addLink(h3, s1, bw=100)

    # Receiver-side link is the constrained campus-egress link, same as baseline.
    net.addLink(s1, h4, bw=BOTTLENECK_MBPS, use_htb=True)

    return net


if __name__ == "__main__":
    setLogLevel("info")
    net = build()
    net.start()
    info("*** Network started. s1 is under os-ken control at %s:%s\n" % (CONTROLLER_IP, CONTROLLER_PORT))
    info("*** Run traffic e.g.: h1 -> h4 (video/UDP), h2 -> h4 (browsing), h3 -> h4 (bulk/TCP)\n")
    CLI(net)
    net.stop()
