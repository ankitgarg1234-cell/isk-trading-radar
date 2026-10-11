# Phase 2: early earnings acceleration and repeatability

**Repeatable 5× performance is not established.** Research milestone dated 11 October 2026. No leverage, deployed strategy changes or trades.

The winning account independently reconciles all 23 trades and 252 daily books: $10,000 → $51,081.81, +410.82%, maximum drawdown −18.00%. All 1,144 archive member hashes match. At 100 bps per side, the account still returns +401.83% before ending liquidation costs; a mechanical cost deduction lowers it to +397.45%.

Thirty original releases support profitability and demand recovery, but positive revenue-growth acceleration was absent in all three main June 2025 winners. WDC's comparable HDD revenue acceleration is −45.29 percentage points, versus −10.39 points from the cache's mixed scope. Its margin improvement remains positive after removing the litigation credit. An earlier MU setup in April 2024 subsequently lost 28.54% over 252 sessions, with −57.82% path drawdown. Company guidance beats are separate from unavailable analyst consensus surprises.

Of 10,275 mature monthly stock observations, 188 pass the existing growth/margin/momentum gates; 58 of these lose money. Median price return is 29.68%, with −31.86% median path drawdown. Fresh qualification has a similar median to persistent qualification and more losses. NI growth acceleration's rank correlation with subsequent price return is approximately zero. These price-only 252-session labels are separate from calendar-year portfolio returns.

The controlled holding experiment contains 264 cash-funded annual accounts: 22 starts × six policies × two cost levels. Initial baskets and quantities match the frozen original selection exactly. No replacement stocks are admitted. For June 2025, monthly equal weights return +392.75%; untouched holding returns +463.52%; monthly 25% cap only returns +420.71%. Across all 22 starts, untouched holding's median is +33.00%, worst return −5.30%, and largest drawdown −34.72%. Its two 5× starts overlap in June/July 2025, representing one cycle. Across starts, company/cluster weights reach 52.91%/93.04%. These empirical frequencies cannot estimate future probabilities.

The earlier-price CSV snapshots are packaged in `history/earlier_prices.zip` on GitHub; extract beside that ZIP to restore the original dated paths. Earlier public Yahoo data adds 42,264 daily rows for 12 live case series covering 2010–2023. WBA/PXD downloads fail and remain missing. This selected-survivor capability probe is separate from a historical S&P 500 universe. Historical consensus, dated membership, delisting proceeds, dividend payable dates and complete released-vintage accounting remain validation blockers.

## Read the evidence

- [Master report](research_report.html), [protocol](PROTOCOL.md), [decision log](DECISION_LOG.md), [ranked next experiments](EXPERIMENT_QUEUE.csv).
- [Independent winner audit](audit/findings.md), [all audit checks](audit/summary.json).
- [MU/STX source record](sources/memory/findings.md), [WDC scope bridge](sources/wdc/findings.md).
- [Screen results and all controls](panel/screen_results.csv), [matched June peers](panel/matched_june2025.csv), [all qualified failures](panel/qualified_failures.csv).
- [Every release-date annual account](stages/release_entry_outcomes.csv).
- [All holding accounts](retention/accounts.csv), [policy summary](retention/summary.csv), [threshold frequencies](retention/empirical_frequencies.csv), [return/drawdown frontier](retention/frontier.csv).
- [Daily NAVs](retention/curves.csv.gz), [trades](retention/trades.csv.gz), [holdings](retention/holdings.csv.gz).
- [Independent checks](verification.json), [validation blockers](VALIDATION_STATUS.json).

## Reproduce

Use Python 3.12, pandas 2.2.3 and numpy 2.3.5. From the repository root:

```sh
python research_5x/phase2/code/replay_published_winner.py
python research_5x/phase2/code/analyze_acceleration.py
python research_5x/phase2/code/quarter_observables.py
python research_5x/phase2/code/release_stage_returns.py
python research_5x/phase2/code/retention_ablation.py
python research_5x/phase2/code/verify_phase2.py
python research_5x/phase2/code/build_phase2_report.py
python research_5x/phase2/code/polish_phase2.py
python research_5x/phase2/code/add_comparisons.py
```

The source reconstruction scripts in `sources/memory` and `sources/wdc` rebuild manually verified extraction tables, preserving source URLs and original vintages. They do not live-parse or redownload the issuer sites.

The original engine and cached prices/fundamentals remain frozen. `phase2_bootstrap.py` supports both the original workspace's separate clone and a repository-root checkout. The full archive auditor requires the original October 11 ZIP and workspace layout. The portable winner replay verifies published winning inputs without claiming to reverify the omitted ZIP.

The optional append-only network probe requires yfinance 1.7.0 installed under `research_5x/vendor`. No credentials, cookie cache or vendor dependencies are published. Failed data acquisitions remain missing. All existing 2024–2026 years have been reused; no untouched holdout or calibrated future 5× probability is claimed.
