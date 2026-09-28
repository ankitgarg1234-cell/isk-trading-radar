# Test Results — ServiceNow Inline Filters

- Full pytest regression suite: **54 passed / 0 failed**
- Overall Python coverage: **69%**
- `app/main.py`: **82%**
- `app/analysis_engine.py`: **79%**
- `app/portfolio_engine.py`: **76%**
- `app/db.py`: **98%**
- `python -m compileall -q app tests`: **PASS**
- `node --check app/static/app.js`: **PASS**
- Direct JavaScript assertions for text/discrete/numeric filter operators: **PASS**

The tests include prior regression coverage for persistence, scanner behavior, company-name analysis resolution, screenshot import, risk-profile persistence, position sizing, entry-state decisions and decision-surface rendering.
