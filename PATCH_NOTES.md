# Cumulative decision-quality patch

This patch includes the earlier decision-quality fixes **plus** explicit reduce/partial-profit/exit rationale.

Included fixes:
- Missing evidence no longer causes automatic REDUCE.
- Imported positions queue analysis and show clearer pending state.
- Analyst score is derived when recommendation-count data exists.
- Consensus target details are displayed when supplied by the current data provider.
- REDUCE / PARTIAL PROFIT / EXIT actions include suggested share count / percentage.
- REDUCE / PARTIAL PROFIT / EXIT actions include an explicit evidence-based reason.
- `.ST` positions render SEK appropriately in position-aware views.
- Regression coverage includes the decision branches above.

Validated against the full V1 codebase: **31 tests passed / 0 failed**.
