#!/usr/bin/env python3
"""
traffic_classifier.py
-----------------------
Week 6 deliverable: automatic, behaviour-based traffic classification.

No manual tagging (no hardcoded ports/IPs treated as ground truth) — the
flow's TIER is inferred purely from how it behaves on the wire:
    - mean/variance of packet size
    - mean/variance of inter-arrival time (this doubles as a live jitter
      estimate, directly comparable to the Week 4 baseline jitter numbers)
    - burstiness ratio (packet-size coefficient of variation)

This is Algorithm 1 in the report, grounded in:
    "Software Defined Network Traffic Classification for QoS Optimization
    Using Machine Learning," Journal of Network and Systems Management,
    Springer Nature, 2025 (Serag et al.) — feature set and the
    small-decision-tree classifier design follow this paper's pipeline.

Design choice: a shallow, interpretable DecisionTreeClassifier (not a deep
model) — matches the plan's "rule-based or lightweight decision-tree
classifier" scope for Week 6, and keeps the classifier defensible/inspectable
for the report (we can print the learned tree and cite exact split
thresholds against the feature ranges reported in Serag et al.).

Two ways to get flows in:
  1. train_and_export(): train on labelled sample flows captured earlier
     with Wireshark/tshark (see docs/README.md for the capture recipe) and
     save the fitted tree to disk.
  2. classify_stream(): sniff live packets (via scapy), group into flows by
     5-tuple, compute a rolling feature window per flow, and yield
     (flow_key, tier) as flows are classified. This is what
     integration/bridge.py (Week 7) consumes.

Usage:
    # one-time training from a labelled CSV of flow-level features:
    python3 traffic_classifier.py --train samples.csv --out model.joblib

    # live classification (needs root for sniffing):
    sudo python3 traffic_classifier.py --live eth0 --model model.joblib
"""

import argparse
import csv
import time
from collections import defaultdict, deque
from statistics import mean, pstdev

TIERS = ["realtime", "besteffort", "bulk"]

# Feature-window size: number of packets per flow considered before a
# classification decision is (re-)issued. Small enough to react quickly,
# large enough to estimate steadiness/burstiness meaningfully.
WINDOW_SIZE = 20


# --------------------------------------------------------------------------- #
# Feature extraction
# --------------------------------------------------------------------------- #
def flow_key(pkt_meta):
    """5-tuple key: (src_ip, dst_ip, src_port, dst_port, proto)."""
    return (pkt_meta["src_ip"], pkt_meta["dst_ip"], pkt_meta["src_port"],
            pkt_meta["dst_port"], pkt_meta["proto"])


def compute_features(sizes, timestamps):
    """
    sizes: list[int] packet sizes (bytes) in the current window
    timestamps: list[float] packet arrival times (seconds) in the current window
    Returns a dict of features used by the classifier.
    """
    if len(sizes) < 2:
        return None

    inter_arrivals = [t2 - t1 for t1, t2 in zip(timestamps, timestamps[1:])]

    mean_size = mean(sizes)
    std_size = pstdev(sizes) if len(sizes) > 1 else 0.0
    mean_iat = mean(inter_arrivals)
    std_iat = pstdev(inter_arrivals) if len(inter_arrivals) > 1 else 0.0

    # Burstiness: coefficient of variation of packet sizes.
    # ~0 = very uniform packet sizes; larger values indicate
    # greater packet-size variation/burstiness.
    burstiness = (std_size / mean_size) if mean_size > 0 else 0.0

    return {
        "mean_size": mean_size,
        "std_size": std_size,
        "mean_iat": mean_iat,
        "std_iat": std_iat,
        "burstiness": burstiness,
        # jitter proxy, directly comparable to the Week 4 baseline UDP jitter figure
        "jitter_estimate_ms": std_iat * 1000.0,
    }


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #
class BehavioralClassifier:
    """
    Thin wrapper around a shallow sklearn DecisionTreeClassifier, with a
    rule-based fallback (used if scikit-learn/model file are unavailable,
    e.g. for a quick classroom demo) so the pipeline never silently breaks.
    """

    FEATURE_ORDER = ["mean_size", "std_size", "mean_iat", "std_iat", "burstiness"]

    def __init__(self, model_path=None):
        self.model = None
        if model_path:
            self._load(model_path)

    def _load(self, model_path):
        import joblib
        self.model = joblib.load(model_path)

    def fit(self, X, y):
        from sklearn.tree import DecisionTreeClassifier
        # max_depth kept shallow (<=4) so the learned rules stay inspectable
        # and defensible in the report, per the Week 6 "lightweight" scope.
        self.model = DecisionTreeClassifier(max_depth=4, random_state=42)
        self.model.fit(X, y)
        return self.model

    def save(self, out_path):
        import joblib
        joblib.dump(self.model, out_path)

    def predict_tier(self, features: dict) -> str:
        if self.model is not None:
            x = [[features[f] for f in self.FEATURE_ORDER]]
            return self.model.predict(x)[0]
        return self._rule_based_fallback(features)

    @staticmethod
    def _rule_based_fallback(features):
        """
        Interpretable fallback rules (used if no trained model is loaded).
        Thresholds set from the qualitative packet-size/steadiness ranges
        for interactive vs. bulk flows discussed in Serag et al. (2025);
        should be re-tuned against your own captured samples before Week 9
        results are finalised.
        """
        mean_size = features["mean_size"]
        burstiness = features["burstiness"]
        mean_iat = features["mean_iat"]

        # Real-time: small, steady packets sent at a steady, short interval
        if mean_size < 400 and burstiness < 0.5 and mean_iat < 0.05:
            return "realtime"
        # Bulk: large packets, sent in bursts
        if mean_size > 1000 and burstiness > 0.8:
            return "bulk"
        return "besteffort"


# --------------------------------------------------------------------------- #
# Training entry point (offline, from a labelled feature CSV)
# --------------------------------------------------------------------------- #
def train_and_export(csv_path, out_path):
    """
    csv_path columns expected: mean_size,std_size,mean_iat,std_iat,burstiness,label
    label in {"realtime","besteffort","bulk"}
    """
    X, y = [], []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            X.append([float(row[f]) for f in BehavioralClassifier.FEATURE_ORDER])
            y.append(row["label"])

    clf = BehavioralClassifier()
    clf.fit(X, y)
    clf.save(out_path)
    print(f"Trained on {len(X)} labelled flows -> {out_path}")
    return clf


# --------------------------------------------------------------------------- #
# Live classification (scapy sniff -> rolling per-flow windows -> tier)
# --------------------------------------------------------------------------- #
def classify_stream(iface, clf: BehavioralClassifier, on_classified=None):
    """
    Sniffs `iface` and yields/callbacks (flow_key, tier, features) once each
    flow has enough packets to form a WINDOW_SIZE feature window.

    on_classified(flow_key, tier, features) -> None
        Called for every (re-)classification. integration/bridge.py (Week 7)
        passes a callback here that POSTs to the controller's /classify route.
    """
    from scapy.all import sniff, IP, TCP, UDP

    windows = defaultdict(lambda: {"sizes": deque(maxlen=WINDOW_SIZE),
                                    "times": deque(maxlen=WINDOW_SIZE)})

    def handle(pkt):
        if IP not in pkt:
            return
        proto = 6 if TCP in pkt else (17 if UDP in pkt else None)
        if proto is None:
            return

        # Ignore pure TCP ACK packets. They are transport-control traffic,
        # not application payload, and would otherwise appear as a separate
        # 5-tuple flow with tiny (~66 B) packets and be misclassified as
        # realtime.
        if TCP in pkt:
            tcp = pkt[TCP]
            if len(tcp.payload) == 0 and tcp.flags == "A":
                return

        sport = pkt[TCP].sport if TCP in pkt else pkt[UDP].sport
        dport = pkt[TCP].dport if TCP in pkt else pkt[UDP].dport
        meta = {"src_ip": pkt[IP].src, "dst_ip": pkt[IP].dst,
                 "src_port": sport, "dst_port": dport, "proto": proto}
        key = flow_key(meta)

        w = windows[key]
        w["sizes"].append(len(pkt))
        w["times"].append(time.time())

        if len(w["sizes"]) == WINDOW_SIZE:
            feats = compute_features(list(w["sizes"]), list(w["times"]))
            if feats:
                tier = clf.predict_tier(feats)
                if on_classified:
                    on_classified(key, tier, feats)

    sniff(iface=iface, prn=handle, store=False)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Behavioral traffic classifier (Week 6)")
    parser.add_argument("--train", help="path to labelled CSV of flow features")
    parser.add_argument("--out", default="model.joblib", help="output path for trained model")
    parser.add_argument("--live", help="interface to sniff for live classification")
    parser.add_argument("--model", help="path to a previously trained model.joblib")
    args = parser.parse_args()

    if args.train:
        train_and_export(args.train, args.out)
    elif args.live:
        classifier = BehavioralClassifier(model_path=args.model)

        def _print(key, tier, feats):
            print(f"[{time.strftime('%H:%M:%S')}] flow={key} -> tier={tier} "
                  f"(mean_size={feats['mean_size']:.0f}B, "
                  f"jitter~{feats['jitter_estimate_ms']:.2f}ms, "
                  f"burstiness={feats['burstiness']:.2f})")

        classify_stream(args.live, classifier, on_classified=_print)
    else:
        parser.print_help()
