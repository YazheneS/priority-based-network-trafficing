#!/usr/bin/env python3
"""
priority_controller.py
-----------------------
Week 5 deliverable: SDN-based priority engine.

Built on os-ken (the actively maintained Ryu fork — Ryu itself is
unmaintained, per team decision) over OpenFlow 1.3.

What this does:
  1. On switch connect, installs a table-miss flow (send unknown packets
     to controller) plus a default LLDP/ARP passthrough.
  2. Installs three tiers of flow rules, each pointing at one of the OVS
     HTB queues created by topology/setup_queues.sh:
         tier 0 = real-time   -> queue 0 (min 6 Mbps, max 10 Mbps)
         tier 1 = best-effort -> queue 1 (min 2 Mbps, max  8 Mbps)
         tier 2 = bulk        -> queue 2 (min 1 Mbps, max 10 Mbps, guaranteed floor)
  3. For Week 5 alone (before the Week 6 classifier and Week 7 integration
     are wired in), a small set of STATIC rules stand in for classification,
     based on transport protocol / port — this keeps Week 5 independently
     testable. classify_and_install() is the single seam Week 7 will call
     into with real classifier output, so nothing here needs to change later.
  4. Exposes a REST API (os_ken.app.wsgi) so the Week 6/7 classifier can push
     dynamic per-flow tier decisions, and the Week 8 dashboard can read
     stats and flip the priority engine ON/OFF.

Fairness logic (guaranteed minimum bandwidth per tier, never full starvation)
follows the bandwidth-splitting approach in:
    Shahriar et al., "Prioritized Multi-Tenant Traffic Engineering for
    Dynamic QoS Provisioning in Autonomous SDN-OpenFlow Edge Networks,"
    arXiv:2403.15975, 2024 (Algorithm 2).

The strict-precedence pitfall (background traffic starved to zero) this
design deliberately avoids is the one critiqued in:
    "QoS Control and Prioritization with SDN," IEEE Document 7130421.

Run (inside WSL2, with os-ken installed: pip install os-ken):
    os-ken-manager --wsgi-config priority_controller.py priority_controller.py
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from os_ken.controller.handler import set_ev_cls
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet, ether_types

# --- Tier -> OVS queue-id mapping (must match topology/setup_queues.sh) ---
QUEUE_REALTIME = 0
QUEUE_BESTEFFORT = 1
QUEUE_BULK = 2

TIER_TO_QUEUE = {
    "realtime": QUEUE_REALTIME,
    "besteffort": QUEUE_BESTEFFORT,
    "bulk": QUEUE_BULK,
}

# Static ports used only for the Week 5 standalone demo, before the real
# classifier (Week 6) is wired in via the REST /classify endpoint (Week 7).
DEMO_VIDEO_UDP_PORT = 5000       # e.g. iperf3 -u -p 5000 (video-like flow)
DEMO_BULK_TCP_PORT = 5201        # iperf3 default TCP port (bulk download-like flow)

INSTANCE_NAME = "priority_api_app"


class PriorityController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}          # dpid -> datapath
        self.priority_engine_on = True   # dashboard ON/OFF toggle (Week 8 hook)
        self.flow_log = []           # recent classify/install events, for dashboard/debug

        self._start_rest_server()

    # ------------------------------------------------------------------ #
    # Switch bring-up
    # ------------------------------------------------------------------ #
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # ARP: allow normal OVS forwarding so hosts can resolve each other.
        arp_match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_ARP
        )
        arp_actions = [
            parser.OFPActionOutput(ofproto.OFPP_NORMAL)
        ]
        self.add_flow(
            datapath,
            priority=100,
            match=arp_match,
            actions=arp_actions
        )

        # Default forwarding for traffic that does not match a QoS rule.
        # This is intentionally lower priority than the QoS rules.
        normal_match = parser.OFPMatch()
        normal_actions = [
            parser.OFPActionOutput(ofproto.OFPP_NORMAL)
        ]
        self.add_flow(
            datapath,
            priority=0,
            match=normal_match,
            actions=normal_actions
        )

        self.logger.info(
            "Switch %s connected; base flows installed.",
            datapath.id
        )

        if self.priority_engine_on:
            self._install_demo_static_rules(datapath)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        kwargs = dict(
            datapath=datapath,
            table_id=0,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout,
            hard_timeout=0,
        )

        if buffer_id is not None:
            kwargs["buffer_id"] = buffer_id

        mod = parser.OFPFlowMod(**kwargs)
        datapath.send_msg(mod)

        self.logger.info(
            "FLOW_MOD sent: priority=%s match=%s actions=%s",
            priority, match, actions
        )

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def error_msg_handler(self, ev):
        msg = ev.msg
        self.logger.error(
            "OpenFlow ERROR: type=%s code=%s data=%s",
            msg.type,
            msg.code,
            getattr(msg, "data", b""),
        )

    # ------------------------------------------------------------------ #
    # Core seam: install a priority flow for one (match, tier) pair.
    # Week 7's classifier bridge calls this indirectly via classify_and_install().
    # ------------------------------------------------------------------ #
    def install_priority_flow(self, datapath, match, tier,
                              out_port=None, priority=10, idle_timeout=30):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        if not self.priority_engine_on:
            # QoS OFF: normal OVS forwarding.
            actions = [
                parser.OFPActionOutput(ofproto.OFPP_NORMAL)
            ]
            self.add_flow(
                datapath,
                priority=priority,
                match=match,
                actions=actions,
                idle_timeout=idle_timeout
            )
            return

        queue_id = TIER_TO_QUEUE.get(tier, QUEUE_BESTEFFORT)

        # Set the queue, then let OVS NORMAL choose the correct output port.
        actions = [
            parser.OFPActionSetQueue(queue_id),
            parser.OFPActionOutput(ofproto.OFPP_NORMAL)
        ]

        self.add_flow(
            datapath,
            priority=priority,
            match=match,
            actions=actions,
            idle_timeout=idle_timeout
        )

        self.flow_log.append({
            "match": str(match),
            "tier": tier,
            "queue": queue_id
        })

        self.logger.info(
            "Installed tier=%s (queue %s) for match=%s",
            tier,
            queue_id,
            match
        )

    def classify_and_install(self, dpid, tier, src_ip=None, dst_ip=None,
                              src_port=None, dst_port=None, ip_proto=None):
        """Single entry point the Week 7 classifier bridge calls over REST."""
        datapath = self.datapaths.get(dpid)
        if datapath is None:
            return False, "unknown datapath %s" % dpid

        parser = datapath.ofproto_parser
        match_kwargs = {"eth_type": ether_types.ETH_TYPE_IP}
        if src_ip:
            match_kwargs["ipv4_src"] = src_ip
        if dst_ip:
            match_kwargs["ipv4_dst"] = dst_ip
        if ip_proto:
            match_kwargs["ip_proto"] = ip_proto
        if ip_proto == 6 and dst_port:   # TCP
            match_kwargs["tcp_dst"] = dst_port
        if ip_proto == 17 and dst_port:  # UDP
            match_kwargs["udp_dst"] = dst_port

        match = parser.OFPMatch(**match_kwargs)
        self.install_priority_flow(datapath, match, tier)
        return True, "ok"

    # ------------------------------------------------------------------ #
    # Week 5 standalone demo rules (static stand-in for the real classifier)
    # ------------------------------------------------------------------ #
    def _install_demo_static_rules(self, datapath):
        parser = datapath.ofproto_parser

        video_match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP, ip_proto=17, udp_dst=DEMO_VIDEO_UDP_PORT
        )
        self.install_priority_flow(
            datapath, video_match, "realtime",
            priority=20, idle_timeout=0
        )

        bulk_match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP, ip_proto=6, tcp_dst=DEMO_BULK_TCP_PORT
        )
        self.install_priority_flow(
            datapath, bulk_match, "bulk",
            priority=20, idle_timeout=0
        )

        # Everything else IP traffic defaults to best-effort.
        default_match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP)
        self.install_priority_flow(
            datapath, default_match, "besteffort",
            priority=5, idle_timeout=0
        )

    def set_priority_engine(self, enabled: bool):
        self.priority_engine_on = enabled
        # Re-push demo/base rules under the new mode so the toggle is
        # visible immediately (dashboard ON/OFF requirement, Week 8).
        for dp in self.datapaths.values():
            self._install_demo_static_rules(dp)

# ------------------------------------------------------------------------ #
# Standalone REST API
# ------------------------------------------------------------------------ #

class _PriorityAPIHandler(BaseHTTPRequestHandler):

    controller = None

    def _send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))

        if length == 0:
            return {}

        body = self.rfile.read(length)

        return json.loads(body.decode("utf-8"))

    def do_GET(self):

        if self.path == "/status":

            controller = self.controller

            self._send_json(
                200,
                {
                    "priority_engine_on": controller.priority_engine_on,
                    "datapaths": list(controller.datapaths.keys()),
                    "recent_flows": controller.flow_log[-50:],
                },
            )

            return

        self._send_json(
            404,
            {"ok": False, "msg": "unknown endpoint"},
        )

    def do_POST(self):

        controller = self.controller

        try:
            body = self._read_json()

            if self.path == "/classify":

                dpid = int(body["dpid"])
                tier = body["tier"]

                if tier not in TIER_TO_QUEUE:
                    self._send_json(
                        400,
                        {"ok": False, "msg": "invalid tier"},
                    )
                    return

                ok, msg = controller.classify_and_install(
                    dpid,
                    tier,
                    src_ip=body.get("src_ip"),
                    dst_ip=body.get("dst_ip"),
                    src_port=body.get("src_port"),
                    dst_port=body.get("dst_port"),
                    ip_proto=body.get("ip_proto"),
                )

                self._send_json(
                    200 if ok else 400,
                    {"ok": ok, "msg": msg},
                )

                return

            if self.path == "/toggle":

                enabled = bool(body.get("enabled", True))

                controller.set_priority_engine(enabled)

                self._send_json(
                    200,
                    {
                        "ok": True,
                        "priority_engine_on": enabled,
                    },
                )

                return

            self._send_json(
                404,
                {"ok": False, "msg": "unknown endpoint"},
            )

        except Exception as exc:

            self._send_json(
                400,
                {
                    "ok": False,
                    "msg": str(exc),
                },
            )

    def log_message(self, fmt, *args):
        return


def _start_rest_server(self):

    _PriorityAPIHandler.controller = self

    self.rest_server = ThreadingHTTPServer(
        ("127.0.0.1", 8080),
        _PriorityAPIHandler,
    )

    self.rest_thread = threading.Thread(
        target=self.rest_server.serve_forever,
        daemon=True,
    )

    self.rest_thread.start()

    self.logger.info(
        "REST API listening on http://127.0.0.1:8080"
    )


PriorityController._start_rest_server = _start_rest_server
