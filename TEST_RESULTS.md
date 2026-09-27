# Data Resilience Patch — Test Results

Command:

`python -m pytest --cov=app --cov-report=term-missing`

Result:

- **35 passed**
- **0 failed**
- **71% overall Python coverage**
- Decision engine: **80%**
- Database layer: **98%**
- Main web application: **82%**
- Market-data layer: **52%** (external-network branches are intentionally mocked rather than calling live providers in regression tests)

The external SEC/Finnhub/Yahoo adapters are unit-tested with deterministic mocked API payloads; live network availability is not claimed by the regression suite.
