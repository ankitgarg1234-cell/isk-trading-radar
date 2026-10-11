# GEM exact archived specification — v1

Frozen in `frozen_config.json` before the narrowed evaluation. This specification recovers code, rather than inventing a replacement for a prose label. Source engines and input hashes are recorded in that file and `archive_reproduction.json`. No original 75/25 strategy or deployed dashboard was run or changed.

## Universe and financial gates

Use the archive's reconstructed historical S&P 500 membership (including effective additions/removals and SATS/ECHO identity alias), not today's constituents. Coverage omissions are audit failures, not defensible economic exclusions. Eligibility requires 126 prior price observations, positive bars, nominal closing price >= $5, and trailing 20-session average vendor closing-price × volume >= $10 million.

Quarterly facts are eligible through the day before the month-end signal. Use 10-Q records only. Prefer direct 60–125-day quarterly values, then the archived derived-quarter field, then Q1 raw values; latest-per-period ordering follows the original filing/acceptance rules. Revenue and earnings inputs older than 210 days by filing date are suppressed. Operating income has no separate freshness suppression. Use the comparator 310–420 days earlier closest to 365 days.

Revenue growth >20%; current net income >0 and either net-income growth >20% or the comparator net income <=0; operating margin improvement >3 percentage points, calculated as 100 × (current operating income/current revenue − comparator operating income/comparator revenue). Revenue denominators must be positive. Positive trailing 63-session price return is required. **Rank solely by r63 descending, stable sort.** Growth, earnings and margin are gates, not weighted score factors. Sector, forward-return labels, analyst estimates, and historical winner names are not used by this configuration.

## Accounts and execution

Five slots at 20% target each, whole shares, unused slots in cash. Start each independent account with $10,000 cash on January's first trading day. The archived simulator only admits newly generated month-end signals: no December warm start; first purchases follow January month-end. Rebalance monthly at the next available session open, reducing positions before adding; cash affordability is enforced. Signals use the completed month's closing bar. No original strategy stop-loss, market-regime filter, leverage, or cash interest. Membership exits follow the archived effective-date convention. Terminal holdings remain marked, without a hypothetical liquidation cost.

Costs are 20 basis points per side (10 fee +10 slippage), charged against gross open-price notional. Stress 100 basis points and additional delays of 1, 5, 20 sessions use the unchanged formula. Daily open bars establish a model price; actual fill liquidity and quotes are uncertified.

Prices restore nominal units using vendor split factors. Ordinary splits change shares. Known archived spinoffs preserve parent shares and distribute children sold at the next available open, with observed-value basis allocation. Nonstandard vendor factors remain uncertified. Cash dividends are credited on ex-date, not payable date. These original accounting assumptions are preserved for reproduction and disclosed as PIT certification limitations. No actually held split/spinoff occurs in the three original or documented retention accounts in these periods; independent reconciliation checks this fact.

## Previously documented retention variants (all frozen, none selected)

* `retain_rank35`: retain incumbents still qualifying and ranked <=35; fill remaining slots from the top 20; continue equal-slot rebalancing.
* `preserve_weights`: ordinary top-five eligibility/selection, but preserve incumbent share drift, trimming positions over 25% at monthly execution. Fill empty slots with available cash, bounded by 20% per slot. The 25% execution cap is not a daily mark-to-market cap.
* `retain_and_preserve`: combine the two documented policies.

The ordinary original has no retention rank or 25% cap. All variants require the same GEM gates; no unlimited hold through fundamental failure.

## Date and evidence conventions

A: 2025-01-02 through 2025-12-31, 250 completed sessions. B: 2026-01-02 through 2026-10-09, 194 sessions, not annualized. C: 2025-01-02 through 2026-10-09, 444 sessions, 645 elapsed calendar days, continuously compounded without a January reset. C CAGR uses actual elapsed calendar days /365.25. Independent B differs from the second year of C because it starts in cash.

2024 price history suffices for the 126-session gate; quarterly comparators sometimes require 2023/2024 filings. No full 2022–2023 market-wide dataset is required. The inherited preparation routine computes unused forward labels; the exported feature table removes those labels, and the frozen GEM decision reads only the contemporaneous gates and r63. No future return participates in selection.

Archive reproduction: 2024-01-02 through 2026-10-01. Exact equality of six recorded accounting metrics is required. This is an accounting/configuration check, not data certification. All 2025–2026 results remain retrospective because this period was previously researched. No genuinely untouched prospective observation exists in this assignment.
