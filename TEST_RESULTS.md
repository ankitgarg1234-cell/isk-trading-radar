# Test Results

Final verification on the cumulative project state used to build this patch:

- Pytest: **69 passed / 0 failed**
- Python compileall: **PASS**
- JavaScript syntax (`node --check app/static/app.js`): **PASS**
- Overall Python coverage: **72%**
- `analysis_engine.py`: **81%**
- `main.py`: **85%**
- `db.py`: **92%**
- `portfolio_engine.py`: **76%**
- `scanner.py`: **75%**

Targeted regression coverage includes:
- score 53 in Primary Buy does not create an attention alert
- 68 Primary Buy -> CONSIDER BUY
- 68–74 Better Buy -> STARTER BUY
- 75–84 Primary/Better -> BUY
- 85+ Primary/Better -> STRONG BUY
- legacy WAIT alerts are hidden from the attention queue
- actionable BUY remains visible
- duplicate active alerts are suppressed/refreshed
- portfolio ROTATE/SWAP proposal becomes an attention alert
- swap scan does not load the full market payload universe
- existing no-panic-sell thesis gates remain covered by the full suite
