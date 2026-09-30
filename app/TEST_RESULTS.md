# Test Results

- Full reconstructed latest dashboard suite: **90 passed / 0 failed**
- `python -m compileall -q app`: passed

New regression coverage includes:
- Periodic disclosure company purchase + amount parsing.
- Multiple adjacent NVIDIA purchase/sale rows stay separate.
- Multiple annual/periodic disclosure sources are checked.
- USAspending indirect reseller/product procurement is detected without counting the prime-award amount as direct company revenue.
- White House investment-tracker evidence is classified as administration context, not government capital.
- Manual stock-detail refresh forces `strategic_refresh=True`.
- Existing shadow factor still does not alter rank-v1/deterministic ranking.
