#!/usr/bin/env bash
#
# capture_besteffort.sh
# -----------------------
# Guides a real besteffort-traffic capture session, addressing Known Issue 1
# in docs/README.md: model.real.joblib has zero besteffort training samples.
#
# This does NOT fabricate traffic that looks like realtime or bulk with a
# different label slapped on - it drives genuinely irregular, moderate-rate
# HTTP-like request/response traffic (short curl bursts with randomised
# gaps) from h2, the host topo.py already designates as the best-effort/
# browsing sender, to h4. That's the same distinction Known Issue 1 asks
# for: "a short HTTP request/response pattern rather than a steady iperf
# stream."
#
# Usage (run from the `mininet>` CLI's xterm for h2, i.e. `mininet> xterm h2`,
# NOT from a regular WSL2 shell - h2 only exists inside the running topology):
#
#   1. In a separate terminal, with the topology already up (topo.py) and
#      h4 reachable:
#        mininet> h4 python3 -m http.server 8000 &
#
#   2. In h2's terminal:
#        bash automation/capture_besteffort.sh <duration_seconds>
#
# Produces a pcap under captures/, then tells you the exact
# extract_besteffort_features.py command to run against it.
set -euo pipefail

DURATION="${1:-30}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAPTURE_DIR="$PROJECT_ROOT/captures"
TS="$(date +%Y%m%d_%H%M%S)"
PCAP_PATH="$CAPTURE_DIR/besteffort_${TS}.pcap"

H2_IP="10.0.0.2"
H4_IP="10.0.0.4"
HTTP_PORT="8000"

mkdir -p "$CAPTURE_DIR"

echo "=== Besteffort traffic capture ==="
echo
echo "This assumes:"
echo "  - You are running this INSIDE h2's shell (mininet> xterm h2, then run this there)"
echo "  - h4 is already serving HTTP on port $HTTP_PORT:"
echo "      mininet> h4 python3 -m http.server $HTTP_PORT &"
echo "  - The controller + bridge are running if you want this traffic to also"
echo "    get classified live (optional for capture - not required to just"
echo "    record the pcap)."
read -rp "Press Enter once h4's HTTP server is confirmed running... "

if ! command -v tcpdump >/dev/null 2>&1; then
  echo "tcpdump not found. Install it first: sudo apt install -y tcpdump"
  exit 1
fi

echo
echo "Capturing on h2-eth0 for ${DURATION}s -> $PCAP_PATH"
echo "(Run this script as root/sudo if tcpdump permission is denied.)"

# Background capture on h2's own interface.
tcpdump -i h2-eth0 -w "$PCAP_PATH" "host $H4_IP" &
TCPDUMP_PID=$!
sleep 1  # let tcpdump attach before traffic starts

echo "Generating irregular HTTP-like request bursts from h2 -> h4 for ${DURATION}s..."
END=$((SECONDS + DURATION))
while [ $SECONDS -lt $END ]; do
  # A short burst of 1-3 requests (like a page load pulling a few assets),
  # then an irregular gap (like a person reading before the next click) -
  # this is what makes it genuinely besteffort-shaped rather than a steady
  # stream: uneven packet timing AND uneven burst sizes.
  BURST_SIZE=$(( (RANDOM % 3) + 1 ))
  for _ in $(seq 1 "$BURST_SIZE"); do
    curl -s -o /dev/null "http://${H4_IP}:${HTTP_PORT}/" || true
  done
  GAP="0.$(( (RANDOM % 8) + 2 ))"   # ~0.2-0.9s irregular gap between bursts
  sleep "$GAP"
done

echo "Stopping capture..."
kill "$TCPDUMP_PID" 2>/dev/null || true
wait "$TCPDUMP_PID" 2>/dev/null || true

echo
echo "Done. Captured: $PCAP_PATH"
echo
echo "Next step - extract labelled features (run outside Mininet, back in your"
echo "normal project shell with the venv activated):"
echo
echo "  python3 automation/extract_besteffort_features.py \\"
echo "      --pcap $PCAP_PATH \\"
echo "      --host-ip $H2_IP \\"
echo "      --out classifier/test_data/besteffort_review.csv"
echo
echo "Then eyeball besteffort_review.csv before appending to real_flows.csv."
echo "Repeat this capture 2-3 times (different random gaps each run) to get"
echo "more than one besteffort sample - a single sample is still a thin"
echo "training set for that tier."
