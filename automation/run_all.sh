#!/usr/bin/env bash
#
# run_all.sh
# -----------
# Convenience wrapper for the automated Table I experiment. This does NOT
# start the controller or the bridge for you (see the header comment in
# experiment_runner.py for why) - it prints reminders and pauses for you
# to confirm each is running, then drives the rest automatically.
#
# Usage:
#   bash automation/run_all.sh [trials] [duration_seconds]
#
set -euo pipefail

TRIALS="${1:-3}"
DURATION="${2:-15}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Campus QoS automated experiment runner ==="
echo
echo "Step 1: is the os-ken controller running?"
echo "  If not, open another terminal and run:"
echo "    cd $PROJECT_ROOT && source .venv/bin/activate"
echo "    osken-manager controller/priority_controller.py"
read -rp "Press Enter once the controller is running... "

echo
echo "Step 2: this script will now bring up Mininet and the QoS queues."
echo "Once the interfaces exist, you'll be prompted to start the bridge"
echo "(integration/bridge.py) in another terminal, if you want the live"
echo "classifier driving flow decisions during the experiment. If you skip"
echo "this, only the controller's static demo rules will apply."
echo

cd "$PROJECT_ROOT"

MODEL_PATH="classifier/test_data/model.real.joblib"
if [ ! -f "$MODEL_PATH" ]; then
  echo "No trained model found at $MODEL_PATH (model files are gitignored,"
  echo "so a fresh clone never has one). Training now from real_flows.csv..."
  echo "NOTE: real_flows.csv currently has zero besteffort samples (Known"
  echo "Issue 1) - add labelled besteffort rows to it before this step if"
  echo "you haven't yet, or the resulting model will only distinguish"
  echo "realtime vs bulk, not all three tiers."
  source .venv/bin/activate
  python3 classifier/traffic_classifier.py \
    --train classifier/test_data/real_flows.csv \
    --out "$MODEL_PATH"
  deactivate
  echo "Model trained: $MODEL_PATH"
  echo
fi

sudo /usr/bin/python3 automation/experiment_runner.py \
  --trials "$TRIALS" \
  --duration "$DURATION" \
  --out results/table1_results.csv \
  --log-dir results/ovs_snapshots

echo
echo "Step 3: summarizing results..."
python3 automation/summarize_results.py --in results/table1_results.csv --out results/table1_summary.csv

echo
echo "Done. See results/table1_summary.csv for the averaged Table I values,"
echo "and results/table1_results.csv for the raw per-trial data."
