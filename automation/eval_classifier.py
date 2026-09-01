#!/usr/bin/env python3
"""
eval_classifier.py
---------------------
Computes standard classifier evaluation metrics (accuracy, precision,
recall, F1, confusion matrix) for classifier/traffic_classifier.py's model,
using a held-out labelled CSV (NOT the same file used for training - if
you evaluate on training data, your numbers are meaningless for the report).

Expects a CSV with columns: mean_size,std_size,mean_iat,std_iat,burstiness,label
(same format as classifier/test_data/test_flows.csv).

Usage:
    source .venv/bin/activate
    python3 automation/eval_classifier.py \
        --model classifier/test_data/model.real.joblib \
        --test-data classifier/test_data/holdout_flows.csv

If you don't have a separate held-out CSV yet, capture a handful of fresh
labelled flows (same process used to build model.real.joblib's training
set - see docs/README.md Task 2 history) and save them to a new CSV first.
Do not reuse test_flows.csv here if that's what the deployed model was
trained on.
"""

import argparse
import csv
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier"))
from traffic_classifier import BehavioralClassifier  # noqa: E402


def load_csv(path):
    X, y = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            X.append({f: float(row[f]) for f in BehavioralClassifier.FEATURE_ORDER})
            y.append(row["label"])
    return X, y


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="path to trained .joblib model")
    parser.add_argument("--test-data", required=True, help="path to held-out labelled CSV")
    args = parser.parse_args()

    from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix, classification_report

    clf = BehavioralClassifier(model_path=args.model)
    X, y_true = load_csv(args.test_data)

    y_pred = [clf.predict_tier(x) for x in X]

    print(f"Evaluated on {len(y_true)} held-out samples from {args.test_data}\n")

    acc = accuracy_score(y_true, y_pred)
    print(f"Accuracy: {acc:.3f}\n")

    labels = sorted(set(y_true) | set(y_pred))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    print(f"{'Tier':<12} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Support'}")
    for label, p, r, f, s in zip(labels, precision, recall, f1, support):
        print(f"{label:<12} {p:<12.3f} {r:<12.3f} {f:<12.3f} {s}")

    print("\nConfusion matrix (rows = true, cols = predicted):")
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    print("        " + "  ".join(f"{l:>10}" for l in labels))
    for label, row in zip(labels, cm):
        print(f"{label:<8}" + "  ".join(f"{v:>10}" for v in row))

    print("\nFull classification report:")
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))

    if len(set(y_true)) < 3:
        print("NOTE: held-out data covers fewer than 3 tiers - these metrics do not "
              "demonstrate 3-tier classification performance (see Known Issue 1: "
              "besteffort training data is still missing).")


if __name__ == "__main__":
    main()
