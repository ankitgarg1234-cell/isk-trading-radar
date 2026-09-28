# Test Results

Regression run after the Decision Dashboard + Risk Management patch:

- **52 passed**
- **0 failed**
- Overall application code coverage: **69%**
- `app/main.py`: **82%**
- `app/analysis_engine.py`: **79%**
- `app/portfolio_engine.py`: **76%**
- `app/db.py`: **98%**

New regression coverage includes:
- target risk-profile persistence
- risk profile changes position sizing without changing the underlying stock score
- Strong Buy surfacing
- buy-zone distance = NOW when price is inside the zone
- account-risk concentration detection
- dashboard search/filter/risk UI presence
- live API decision-surface fields
- all previous scanner, persistence, screenshot import, data resilience, buy-zone and sell-safety tests

Command used:

```bash
python -m pytest --cov=app --cov-report=term-missing -q
```
