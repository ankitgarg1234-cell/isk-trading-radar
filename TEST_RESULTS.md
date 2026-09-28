# Test Results — Database Egress Optimization

Final verification:

- Pytest: **60 passed / 0 failed**
- Python compile check: **PASS**
- JavaScript syntax check: **PASS**
- Overall Python coverage: **65%**
- `analysis_engine.py`: **81%**
- `main.py`: **84%**
- `db.py`: **92%**
- `portfolio_engine.py`: **76%**
- `scanner.py`: **73%**

New targeted regression tests verify:
- current-state payloads exclude heavy price-history arrays;
- sector-benchmark history is excluded from current-state payloads;
- repeated unchanged scans do not create duplicate historical snapshots;
- material action changes create a new historical snapshot immediately;
- historical snapshot payloads are compact;
- the dashboard renders from `RadarCandidate.current_json` with no `AnalysisSnapshot` required;
- repeated `/api/live` calls reuse the server-side cache;
- live browser polling is no longer configured at an aggressive 15-second cadence;
- existing persistence, screenshot import, portfolio risk, alert management, no-panic-sell logic, ServiceNow filters and company-name analysis tests remain green.
