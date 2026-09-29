# Test Results

- Command: `pytest -q tests`
- Result: **84 passed / 0 failed**
- Python compileall: passed

New regression coverage verifies:
- Government equity / administration action is not misclassified as Donald Trump personal investment.
- Donald Trump personal-interest mentions and Trump-family mentions stay separate.
- Strategic-capital evidence is shadow-only and cannot change rank-v1.
- Federal-award materiality can be normalized to company revenue.
- Compact payload/event limits protect managed-Postgres egress.
