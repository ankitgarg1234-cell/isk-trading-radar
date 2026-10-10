# Global five-stock historical comparison: final research report

**OUTCOME B — EXTERNALLY BLOCKED.** Checked 10 October 2026,
Europe/Stockholm, on `research/eodhd-acwi-imi-setup`.

The requested comparison is 1 October 2023–30 September 2026, $10,000,
original S&P 500 versus **SPGM HISTORICAL ETF HOLDINGS PROXY**. The offline
engine, code/synthetic parity, SEC-only universe and automatic continuation
are implemented. Historical execution and attribution are blocked by missing
rights-permitted dated classifications/listings and complete price/FX inputs.
No historical investment performance is asserted. Nine of sixteen readiness
requirements fail. No threshold or strategy parameter was weakened.

## Completed work and validation

| Phase | Result | Evidence |
|---|---|---|
|0: verify prior work|COMPLETE|Verified six prior reports, strategy authority,71 existing research tests,21 portfolios/48 original universes; existing local work pushed before this task|
|1: isolated historical engine|COMPLETE for validated fixtures|Source-pinned original five-stock functions, offline global event/FX/action accounting and reconciled metrics|
|2: strategy parity|COMPLETE code/synthetic; historical parity unverified|Six independent replay comparison categories pass; no matching historical five-stock oracle located|
|3: universe|COMPLETE|48 separately frozen SEC-only decisions; actual NY16:20 month-end/DST times; initial September29 2023 signal|
|4: classifications/listings|BLOCKED|0% historically verified GICS and listing maps; licensed historical extract absent|
|5: historical inputs|BLOCKED; inventory/resumption complete|539 legacy series,14 EODHD raw series; no eligible prelaunch warm-up, reference histories or FX|
|6: readiness|COMPLETE, FAIL|16 checks:7 pass,9 fail; cache-only paired runner fails closed|
|7: historical A/B execution|BLOCKED|No admissible complete historical input bundles|
|8: historical attribution|BLOCKED|No historical trades/NAV from qualifying replay|
|9: final outputs|COMPLETE for externally blocked outcome|This report, final readiness, master status, ignored machine-readable checkpoints and exact input schema|

Final validation: **104 research tests passed**, plus **16 existing paper-trial
tests passed** against an isolated in-memory database. The replay compares
NAV/cash/share quantities, final holding cost/peak/stop state, selected
stocks/weights/raw ranks/targets, dated fills/fees/stops, lockouts and sector
regimes/exposure caps. Its500 stocks and12 references are explicitly synthetic,
with260 warm-up sessions and four replay sessions. Historical performance
parity is not established. See [SP500_PARITY_REPORT.md](SP500_PARITY_REPORT.md).

Original holdings/snapshot inputs, all97 original compressed universe exports
and16 inventory source files retain their recorded SHA256 hashes. Live/paper
strategy modules remain unchanged. No broker, real trade, purchase or paid
download was used; raw data, outputs and credentials remain outside Git.

## Data sources and universe methodology

The cache contains21 source portfolios:17 SEC N-PORT portfolios and four
archived publisher workbooks. For this comparison **membership is SEC-only**:
at each decision use the latest SEC portfolio already public strictly before
that timestamp, retaining original portfolio date, publication/acceptance time,
filing, typed identifiers and source hash. A portfolio date is never treated
as its public date. Earlier prior-public exact-ID ticker observations can
supply metadata, but a newer incomplete workbook cannot replace membership.

The new48-date audit contains **128,469 confirmed security-months**, with
**2,403–2,910** common equities and **58–123-day** source ages. **23,730**
security-months have ticker observations (**18.47%**), not verified venue maps;
**32,855** have a source LEI gap (**25.57%**). LEI gaps are not proof that a
company is unidentifiable through other typed IDs. Historical GICS and dated
listing verification both remain **0%**. Country, sector-gap and priority-name
matrices remain under ignored `sec_only_decision_universe/`; the full monthly
matrix is in [SPGM_SEC_ONLY_UNIVERSE.md](SPGM_SEC_ONLY_UNIVERSE.md).

36 target month ends and the prelaunch September29 2023 decision are supported
by lagged membership evidence. This does **not** mean36 executable portfolios:
none yet passes all strategy-input gates. CONFIRMED describes common-equity
membership; its strategy-input status remains UNRESOLVED. Missing identifiers,
provisional evidence and ineligible holdings are retained separately. No
present-day list fills gaps and no missing historical stock is assumed absent.

SPGM is a sampled ETF portfolio, not official MSCI ACWI IMI constituents.
Quarterly disclosure lag, sampling, instrument classification and security/issuer
ambiguity remain structural limitations even after all input gaps are repaired.
Existing MSCI comparison counts and archive-source limitations are documented
in [SPGM_PROXY_REPORT.md](SPGM_PROXY_REPORT.md). Fund aggregate sector weights,
current classifications and SIC/NAICS cannot substitute for historical GICS.

## Preserved strategy and disclosed global mechanics

`dual_momentum/trial.py` is the authority. The20-stock `rules.py` engine and
75/25 leadership experiments are separate strategies. The research kernel
pins the exact original pure functions/constants and fails on source drift.
Five holdings,63/126/252-session scores, raw/risk-adjusted rankings, EMA50/200,
SPY-relative filtering, Top15 retention, five-session lockout, original weights,
2% reserve, sector caps/breadth/exposure,3.5ATR trailing stops, monthly rotation,
7bp modeled fills, $1/$0.005-share commissions and daily risk reviews remain.
SPY and all11 original U.S. sector ETFs remain the reference signals.

Global adapters use actual venue openings, native daily OHLC/ATR/stop coordinates,
USD FX-inclusive signal/valuation accounting and time-ordered cash. Later-market
sales cannot fund earlier-market buys. Missing opens expire; missing real
sessions cannot compress momentum windows. A material country cannot disappear
inside the95% global coverage gate. USD identity-FX U.S. fixtures match original
logic. The terminal reference close marks holdings without forced liquidation.

Foreign daily stop FX uses the prior-observable session-opening quote; proceeds
are released conservatively when the daily bar becomes public. This is a disclosed
execution approximation, not an inferred intraday fill time. The local0.01 stop
floor and original cash-dividend-ledger limitation are preserved. Dividend effects
enter TR momentum, but no explicit cash-dividend credits are invented. Entire
supplied-history EMA seeds are fixed; unknown historical Yahoo download windows
cannot be reconstructed. Complex spin-offs, delisting recoveries, quote-unit
migrations and fractional cash-in-lieu require validated adapters/evidence.
See [HISTORICAL_ENGINE.md](HISTORICAL_ENGINE.md).

AZN's February2 2026 representation conversion, genuine July31 Korean rebounds
and the user-confirmed Taiwan July10 closure regression cases remain preserved.
Original Hon Hai/ASE closed-session observations are retained; confirmed
non-trading sessions are excluded only from derived inputs, never guessed/redated.
These cases demonstrate validation behavior, not full-universe action coverage.

## Readiness failures and exact external deliverables

| Failed requirement | Evidence | Required resolution |
|---|---|---|
|Historical sectors|0% verified;≥98% monthly/≥95% material-country minimum;100% usable/held/selected required|Rights-permitted GICS company/security history with taxonomy, effective intervals and publication/first-known timing|
|Historical listings|0% dated verified|Global security master: ISIN/CUSIP/SEDOL/LEI/issuer links, historical ticker aliases, MIC, share class/ADR ratios, listing/delisting, currency/units and knowledge timing|
|Price warm-up|0 of539 staged and0 of14 EODHD series have253 prelaunch bars; staged maximum211|Raw daily OHLCV plus separate coherent adjusted/TR series, preferably January2021 onward; actual IPO exclusions, inactive securities and fixed source/adjustment vintages|
|Reference histories|SPY plus all11 sector ETFs absent from staged cache|Complete matching reference history;254 actual reference bars for the initial two-close regime and253 stock/sector momentum bars|
|FX|0 verified historical tapes|Positive correctly directed USD-per-major-unit rates with observation/public times at required close/open events; synchronous cross legs;≤5-day age|
|Actions|Examples verified; no complete history|Source-backed split/representation/dividend/complex-event and delisting handling for all used windows; no unexplained discontinuities|
|Global calendars|XNYS and closure fixtures pass; full venue coverage absent|Official/verified session, half-day, suspension/extraordinary-closure and timezone history matching every used bar|
|S&P baseline|January2024 starting membership/undated sectors cannot establishSeptember2023|Prior-public historicalSeptember2023 membership plus dated changes and classifications throughout comparison|
|Missing-security sensitivity|Cannot bound rankings/breadth without missing inputs|Resolve missing potentially qualifying names; assess Top15/Top5, sector/country and signal-coverage impacts before claims|

For all usable data require zero contradictory identifiers,≥99% resolved issuer
links and100% among holdings/raw Top15/entries. Full-proxy faithful rankings
require100% coverage or a documented rule-consistent exclusion. The exploratory
98% gate alone cannot prove that a missing top-ranked stock is irrelevant.
The universe signal gate is≥95%, material-country signals≥90%, and each sector
retains the original90% breadth coverage gate. Source age≤125 days is only the
chosen lagged-proxy convention, not a claim of current monthly constituents.
The bundle loader is deliberately stricter on sectors/listings: every admitted
member must have verified metadata. No Unknown-sector bucket is traded.

An existing authorized MSCI/S&P GICS Direct or distributor historical extract
is a possible classification route. WRDS Compustat historical global fields,
coverage and knowledge dates need entitlement verification; public manuals
redirected to login. These are required field specifications, not instructions
to purchase a subscription. Dated issuer announcements/archived explicit-GICS
holdings may verify individual records but do not currently provide the full
global history. Exact contracts are in [HISTORICAL_DATA_BLOCKERS.md](HISTORICAL_DATA_BLOCKERS.md).

One new EODHD **account** HTTP check consumed **zero endpoint-cost units**.
It reports Free, daily cap20 and usage17 onOctober9; remaining3 belongs to
that reported date. October10 allowance remains unknown. No reset was assumed
and no new price/split/symbol/FX API request was made. Free's approximately
one-year range cannot provide2021–26 even if the daily quota resets.

Independent free ECB preparation added a tested SDMX CSV parser with same-date
USD/EUR cross derivation, revision checks and explicit unverified publication
timing. No candidate rate is automatically admitted for execution. Public
ECB terms/reference/archive attempts failed with proxy403; no archive was
obtained and research/reuse rights were not verified. The saved environment
draft additively includes `www.ecb.europa.eu`, `data-api.ecb.europa.eu` and
continuation instructions, preserving prior settings. Review/save and publish
in environment settings is needed to activate it. ECB currency coverage and
historical executable fixing timing would still require separate validation.

## Performance comparison and attribution

**Unavailable is not a zero return.** The comparison period and starting capital
are fixed, but no real historical replay was executed. Machine-readable readiness
stores `performance_comparison: null`. Synthetic NAV/trades are separately labeled
and cannot be used here.

| Requested measure | S&P500 | SPGM proxy |
|---|---|---|
|Total return / CAGR|Unavailable|Unavailable|
|Maximum drawdown / drawdown dates|Unavailable|Unavailable|
|Annual volatility / Sharpe / Sortino|Unavailable|Unavailable|
|Win rate / average holding period|Unavailable|Unavailable|
|Turnover / average invested capital|Unavailable|Unavailable|
|Cash drag / stop-loss impact|Unavailable|Unavailable|
|Sector / individual-stock contributions|Unavailable|Unavailable|

The engine supplies daily NAV, actual decisions/scores/ranks/weights, quantities,
orders/trades/stops, fees, exposure and reconciled FIFO/stock/sector P&L after
both admitted configurations complete. Sharpe/Sortino use zero risk-free rate.
Observed cash fractions and stopped-lot P&L are not causal cash-drag/stop-benefit
estimates; those require additional controlled simulations.

| Annual period | S&P500 | SPGM proxy |
|---|---|---|
|2023 (Oct–Dec)|Unavailable|Unavailable|
|2024|Unavailable|Unavailable|
|2025|Unavailable|Unavailable|
|2026 (Jan–Sep)|Unavailable|Unavailable|

| Monthly period | S&P500 | SPGM proxy |
|---|---|---|
|2023-10|Unavailable|Unavailable|
|2023-11|Unavailable|Unavailable|
|2023-12|Unavailable|Unavailable|
|2024-01|Unavailable|Unavailable|
|2024-02|Unavailable|Unavailable|
|2024-03|Unavailable|Unavailable|
|2024-04|Unavailable|Unavailable|
|2024-05|Unavailable|Unavailable|
|2024-06|Unavailable|Unavailable|
|2024-07|Unavailable|Unavailable|
|2024-08|Unavailable|Unavailable|
|2024-09|Unavailable|Unavailable|
|2024-10|Unavailable|Unavailable|
|2024-11|Unavailable|Unavailable|
|2024-12|Unavailable|Unavailable|
|2025-01|Unavailable|Unavailable|
|2025-02|Unavailable|Unavailable|
|2025-03|Unavailable|Unavailable|
|2025-04|Unavailable|Unavailable|
|2025-05|Unavailable|Unavailable|
|2025-06|Unavailable|Unavailable|
|2025-07|Unavailable|Unavailable|
|2025-08|Unavailable|Unavailable|
|2025-09|Unavailable|Unavailable|
|2025-10|Unavailable|Unavailable|
|2025-11|Unavailable|Unavailable|
|2025-12|Unavailable|Unavailable|
|2026-01|Unavailable|Unavailable|
|2026-02|Unavailable|Unavailable|
|2026-03|Unavailable|Unavailable|
|2026-04|Unavailable|Unavailable|
|2026-05|Unavailable|Unavailable|
|2026-06|Unavailable|Unavailable|
|2026-07|Unavailable|Unavailable|
|2026-08|Unavailable|Unavailable|
|2026-09|Unavailable|Unavailable|

**2023 diagnosis:** original five-stock underperformance is not established by
an authoritative matching record. Older20-stock/leadership reports cannot prove
that premise. No global improvement or missed-return diagnosis is made.

**2024–25 and2026 leadership:** historical membership evidence can identify
leader appearances, including international semiconductor holdings retained by
the SEC-only policy. Eligibility alone does not establish qualified momentum,
rank, selection, sizing, holding or exit. Without verified sectors/prices/FX,
no claim is made that Korean/Taiwanese memory-chip leadership improved returns
or risk. Priority-company audit matrices are diagnostics, not a restricted
investment list. Full-universe deficiencies cannot be repaired by choosing
successful semiconductor names after observing outcomes.

**Conclusion:** whether global selection improves return, drawdown, consistency,
risk-adjusted performance or preference versus the original strategy is
**undetermined**. Missing-input and proxy-sampling sensitivity remains a blocker
rather than a claimed negligible effect.

## Exact continuation and retained outputs

Provide the historical datasets/evidence above without credentials in files,
then assemble ignored `historical_backtest/input_bundle_manifest.json` with
both `SP500` and `SPGM_PROXY` configurations. The full schema, first decision,
source timing, all-daily membership checks, price/FX/action contracts and
checksum requirements are in
[HISTORICAL_INPUT_BUNDLE_FORMAT.md](HISTORICAL_INPUT_BUNDLE_FORMAT.md).

Refresh source-matched parity, then run:

```bash
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.parity_harness
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.global_backtest_pipeline --resume
```

After complete input admission the runner **automatically proceeds** to paired
replay and reproducible metrics; it makes no EODHD/broker calls. Failed admission
publishes no comparison. Inputs are checked against prior-public daily SEC
member sets, metadata effective/known intervals, pinned source rules and actual
replay availability/coverage/accounting. No boolean ready flag bypasses admission.

Ignored outputs under `research/eodhd_output/spgm_proxy/historical_backtest/`:
readiness JSON/Markdown, price inventory CSV/JSON and input hashes, sanitized
account/request-cost ledgers, synthetic parity receipt and fixture audits,
ECB retrieval-failure manifest, and final blocked checkpoint. Real results/
performance/holdings/trades/attribution exports will be created only after a
valid replay; placeholder historical datasets are not manufactured.

Milestone commits:90f5e54,74ba9bc,3347462,017320c,07c03d0,2efe712 and the
phase6 commit recorded in [GLOBAL_BACKTEST_MASTER_STATUS.md](GLOBAL_BACKTEST_MASTER_STATUS.md).
The final report/checkpoint commit is identified by `git log -1`; all completed
research milestones are pushed to the same research branch.
