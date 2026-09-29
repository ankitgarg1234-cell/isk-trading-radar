# Test Results

- Pytest: **74 passed / 0 failed**
- Python compileall: **PASS**
- JavaScript `node --check`: **PASS**
- Overall Python coverage: **72%**
- `portfolio_engine.py`: **81%**
- `paper_engine.py`: **63%**

New regression coverage verifies:
- Radar display capped at 20.
- Serious shortlist capped at 10.
- Optimizer portfolio does not exceed 7 positions.
- It does not force five positions when fewer candidates qualify.
- AI remains confirmation-only and does not alter Portfolio Priority arithmetic.
- $10,000 paper account initializes and preserves non-negative cash/whole-share sizing.
- Optimizer rotation alerts remain available when live gating is explicitly enabled.
