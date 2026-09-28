# Regression Test Results

Command: `pytest -q`

Result: **43 passed / 0 failed**

New coverage includes:
- market-wide universe is included rather than a fixed seed list
- more than 12 names are processed by the broad-market prefilter
- positions/watchlist remain prioritized
- manual analysis accepts a company name and resolves it to a ticker
- existing V1 ledger/import/decision/persistence tests remain green
