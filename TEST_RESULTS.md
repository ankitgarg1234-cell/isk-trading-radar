# Test results

Reconstructed current dashboard with all prior production patches, then overlaid this fix.

- `pytest -q`: **92 passed / 0 failed**
- `python -m py_compile` on changed runtime files: **passed**

New regression coverage includes:
- USAspending component failure returns partial results and schedules automatic retry instead of exposing `HTTPStatusError`.
- Market-closed scanner cycles still execute strategic-capital background enrichment.
- Existing government/Trump disclosure, optimizer, scanner, paper-trading, alerts, web UI and decision tests remain green.
