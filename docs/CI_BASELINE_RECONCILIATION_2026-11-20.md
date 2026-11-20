# Synthetic scoring gate reconciliation, 20 Nov 2026

The existing CI compared `practice_review_queue.json` (13 synthetic cases) to
two checked-in baselines created for an earlier 9-case version of that dataset.
The harness correctly refused the comparison because the dataset fingerprint
and case set differed. This failed on the original `main` tree before any RTC
code ran.

The two baselines were regenerated from the current 13-case dataset, with five
repeats per case. Before replacing them, all nine shared cases were compared
to the old baselines: **zero changes** in mean total scores and each reported
dimension for both the heuristic and robust scorers. The four additional
cases are new baseline entries, not evidence of real-world scoring accuracy.
The previous 9-case baseline files remain available in Git history at
`3a357e052512f01e5ede62233436cc540588f591`.
