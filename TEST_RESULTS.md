# Test Results

Final verification after the alert-management/no-panic-sell patch:

- Pytest: **59 passed / 0 failed**
- Python compile check: **PASS**
- JavaScript syntax check (`node --check app/static/app.js`): **PASS**
- Overall Python coverage: **70%**
- `analysis_engine.py`: **81%**
- `main.py`: **83%**
- `db.py`: **94%**
- `portfolio_engine.py`: **76%**
- `scanner.py`: **65%**

Targeted regression coverage includes:
- no panic REDUCE from weak momentum / low score alone
- technical stop break does not auto-exit an intact thesis
- verified fundamental deterioration can trigger REDUCE with an explicit share plan
- duplicate active alerts are refreshed rather than duplicated
- alert drill-down endpoint
- dismiss and snooze actions
- clickable alert UI with dismiss cross
- visible System/AI conviction filters
