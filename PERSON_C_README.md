Person C — Classifier Results and Debugging
1. Classifier Evaluation
The final traffic classifier was evaluated using a completely fresh held-out dataset containing 288 samples. The dataset was balanced across the three traffic classes, with 96 realtime, 96 besteffort, and 96 bulk samples. These samples were kept separate from the training data and were not used to retrain the model.
2. Classification Results
The trained Decision Tree classifier achieved an overall accuracy of 97.6%, correctly classifying 281 out of 288 held-out samples. The class-wise performance is shown below.
Traffic Tier	Precision	Recall	F1-score	Support
besteffort	1.000	1.000	1.000	96
bulk	0.989	0.938	0.963	96
realtime	0.941	0.990	0.964	96
The results show that all 96 besteffort samples were classified correctly. Bulk traffic achieved 98.9% precision and 93.8% recall, while realtime traffic achieved 94.1% precision and 99.0% recall.
3. Confusion Matrix
Actual / Predicted	Besteffort	Bulk	Realtime
Besteffort	96	0	0
Bulk	0	90	6
Realtime	0	1	95
The confusion matrix contains seven misclassified samples in total. Six bulk samples were classified as realtime, one realtime sample was classified as bulk, and no besteffort samples were misclassified.
4. Final Feature Set
The classifier uses six behavioral network features to characterize traffic:
•	mean_size — average packet size
•	std_size — variation in packet size
•	mean_iat — average inter-arrival time between packets
•	std_iat — variation in packet inter-arrival time
•	burstiness — relative variation in packet size
•	byte_rate — amount of data transmitted per unit time
5. Debugging and Development Story
The classifier required several rounds of debugging before reaching the final reliable version. During the initial development, the traffic classes showed overlap and some bulk traffic was difficult to distinguish from realtime traffic using the existing behavioral features. The feature set was therefore extended with byte_rate, providing the classifier with an explicit measure of traffic volume over time and improving its ability to distinguish rate-limited realtime traffic from high-rate bulk traffic. Further problems appeared during live-path testing. The live classifier was initially using the wall-clock timestamp from time.time(), which did not correctly represent the timestamp of each captured packet and affected inter-arrival-time calculations. This was corrected by using the packet capture timestamp, float(pkt.time). In addition, TCP ACK/control packets were being handled incorrectly because the original filtering logic relied on an exact TCP-flags match. The live path was changed to use payload length so that TCP packets without application data were excluded from feature calculation. NIC offloading was also disabled before live classification to avoid packet-processing artifacts. After these fixes, the targeted live bulk test correctly identified uncapped TCP bulk traffic as bulk, and the final fresh held-out evaluation achieved 97.6% accuracy across all three traffic classes.
6. Final Result
The final classifier was validated on 288 fresh held-out samples and achieved 97.6% overall accuracy. The result demonstrates that the classifier can distinguish realtime, besteffort, and bulk traffic using packet-level behavioral features. The debugging process also confirmed that reliable live classification depends not only on the machine-learning model, but also on correct packet timestamps, appropriate TCP packet filtering, and controlled network-interface behavior.
7. Person C Phase 3 Contribution
•	Prepared the classifier-results section for the final project report.
•	Documented the 97.6% accuracy obtained from 288 fresh held-out samples.
•	Included class-wise precision, recall, F1-score, and the confusion matrix.
•	Documented the classifier debugging and live-path fixes.
•	Provided the final classifier feature set and interpretation of the results.
