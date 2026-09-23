




# Person C — Classifier Results and Debugging

## 1. Classifier Evaluation

The final traffic classifier was evaluated using a completely fresh **held-out dataset containing 288 samples**.

The dataset was balanced across the three traffic classes:

| Traffic Class | Samples |
|---|---:|
| Realtime | 96 |
| Besteffort | 96 |
| Bulk | 96 |
| **Total** | **288** |

These samples were kept separate from the training data and were **not used to retrain the model**.

---

## 2. Classification Results

The trained **Decision Tree classifier** achieved an overall accuracy of **97.6%**, correctly classifying **281 out of 288** held-out samples.

### Class-wise Performance

| Traffic Tier | Precision | Recall | F1-score | Support |
|---|---:|---:|---:|---:|
| Besteffort | 1.000 | 1.000 | 1.000 | 96 |
| Bulk | 0.989 | 0.938 | 0.963 | 96 |
| Realtime | 0.941 | 0.990 | 0.964 | 96 |

The results show that:

- All **96 besteffort samples** were classified correctly.
- **Bulk traffic** achieved 98.9% precision and 93.8% recall.
- **Realtime traffic** achieved 94.1% precision and 99.0% recall.
- Overall, **281 of 288 samples** were correctly classified.

> **Overall Accuracy: 97.6%**

---

## 3. Confusion Matrix

The confusion matrix shows the actual traffic class against the class predicted by the classifier.

| Actual / Predicted | Besteffort | Bulk | Realtime |
|---|---:|---:|---:|
| **Besteffort** | **96** | 0 | 0 |
| **Bulk** | 0 | **90** | 6 |
| **Realtime** | 0 | 1 | **95** |

### Misclassification Summary

There were **7 misclassified samples** in total:

- **6 bulk samples** were classified as realtime.
- **1 realtime sample** was classified as bulk.
- **0 besteffort samples** were misclassified.

The remaining classification errors therefore occurred only between the **bulk** and **realtime** traffic classes.

---

## 4. Final Feature Set

The classifier uses **six behavioral network features** to characterize traffic.

| Feature | Description |
|---|---|
| `mean_size` | Average packet size |
| `std_size` | Variation in packet size |
| `mean_iat` | Average inter-arrival time between packets |
| `std_iat` | Variation in packet inter-arrival time |
| `burstiness` | Relative variation in packet size |
| `byte_rate` | Amount of data transmitted per unit time |

These features describe both the **packet-level behavior** and **traffic-rate characteristics** of each flow.

The addition of `byte_rate` provided an explicit measure of traffic volume over time, helping distinguish **rate-limited realtime traffic** from **high-rate bulk traffic**.

---

## 5. Debugging and Development Story

The classifier required several rounds of debugging before reaching the final reliable version.

### 5.1 Initial Traffic-Class Overlap

During the initial development, the traffic classes showed overlap and some bulk traffic was difficult to distinguish from realtime traffic using the existing behavioral features.

To improve the feature representation, the classifier was extended with:

```text
byte_rate


This feature provides an explicit measure of the amount of data transmitted per unit time and improved the classifier's ability to distinguish rate-limited realtime traffic from high-rate bulk traffic.

5.2 Live Timestamp Issue

Further problems appeared during live-path testing.

The live classifier was initially using the wall-clock timestamp:

time.time()

This did not correctly represent the timestamp associated with each captured packet and affected inter-arrival-time calculations.

The implementation was corrected to use the packet capture timestamp:

float(pkt.time)
5.3 TCP ACK / Control Packet Filtering

Another issue was found in the handling of TCP packets.

The original filtering logic relied on an exact TCP-flags match, which could incorrectly handle TCP ACK/control packets.

The live path was changed to use payload length so that TCP packets without application data were excluded from feature calculation.

This prevented TCP control packets from distorting the behavioral features.

5.4 NIC Offloading

NIC offloading was also disabled before live classification to avoid packet-processing artifacts.

ethtool -K <interface> tso off gso off gro off
5.5 Final Live Verification

After these fixes, the targeted live bulk test correctly identified uncapped TCP bulk traffic as:

tier=bulk

The final fresh held-out evaluation achieved 97.6% accuracy across all three traffic classes.

6. Final Result

The final classifier was validated on 288 fresh held-out samples and achieved:

Metric	Result
Total held-out samples	288
Correct predictions	281
Incorrect predictions	7
Overall accuracy	97.6%
Besteffort samples	96
Bulk samples	96
Realtime samples	96

The result demonstrates that the classifier can distinguish realtime, besteffort, and bulk traffic using packet-level behavioral features.

The debugging process also confirmed that reliable live classification depends not only on the machine-learning model, but also on:

Correct packet timestamps
Appropriate TCP packet filtering
Controlled network-interface behavior
A suitable behavioral feature set
7. Person C — Phase 3 Contribution

The following work was completed as part of Person C's Phase 3 contribution:

Prepared the classifier-results section for the final project report.
Documented the 97.6% accuracy obtained from 288 fresh held-out samples.
Included class-wise precision, recall, F1-score, and support.
Included the confusion matrix and misclassification analysis.
Documented the classifier debugging and live-path fixes.
Documented the final six-feature classifier feature set.
Explained the role of byte_rate in distinguishing realtime and bulk traffic.
Documented the packet timestamp correction using float(pkt.time).
Documented the TCP payload-based filtering correction.
Documented NIC offloading control for reliable live classification.
Verified the final live bulk classification behavior.
Provided the final classifier results and interpretation for integration into the project report.


## Final Classifier Summary

| Component | Final Result |
|---|---|
| Classifier | Decision Tree |
| Traffic Classes | Realtime, Besteffort, Bulk |
| Features | 6 behavioral features |
| Evaluation Dataset | Fresh held-out dataset |
| Samples | 288 |
| Samples per Class | 96 |
| Correct Predictions | 281 |
| Incorrect Predictions | 7 |
| Accuracy | **97.6%** |
