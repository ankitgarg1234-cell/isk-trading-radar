# Test results

- Full reconstructed latest dashboard regression suite: **78 passed / 0 failed**
- Python compilation: passed
- Added regression coverage for:
  - immediate event-driven entry despite a recent daily rebalance;
  - event-driven entries not postponing the daily rotation clock;
  - low-egress normal cycle loading only held symbols;
  - material-change detection suppressing duplicate optimizer reruns.
