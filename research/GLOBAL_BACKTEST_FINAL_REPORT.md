# S&P500 → Global Momentum Backtest: exploratory continuation

**OUTCOME B — EXTERNALLY BLOCKED.** Continued from 8c3116b on
`research/eodhd-acwi-imi-setup`, checked 10 October 2026. Target remains
October 2023–September 2026, $10,000, original five-stock S&P500 versus
**SPGM HISTORICAL ETF HOLDINGS PROXY**, SEC-only lagged portfolios.

The approved current-GICS exception is implemented. Historical classifications
are optional for the first exploratory run. Real execution is still blocked
by missing sourced classification joins,dated membership/listing evidence,
warm-up/reference prices,FX and complete corporate-event accounting. No
historical comparison was run and no synthetic result is presented as one.
The prior strict checkpoint remains recoverable at commit8c3116b.

## Completed continuation

| Step | Result | Evidence |
|---|---|---|
|1: checkpoint verification|COMPLETE|Requested documents read,104 prior research tests pass,original caches preserved|
|2: two classification modes|COMPLETE implementation|Strict unchanged;current-GICS/correction provenance,coverage and decision sensitivity;10 new regressions|
|3: U.S. inputs|BLOCKED after source investigation|Public history/current-GICS candidates retrieved with publisher licenses;aliases/timing/prices unresolved|
|4: IBKR access|BLOCKED after runtime investigation|No Codex interface,binding,session,client library or local listener;pilot not executed|
|5: global listing maps|BLOCKED after exact-ID audit|7792 current candidate security-months;0% dated verification|
|6: global prices/FX|BLOCKED after cache inventory|539 legacy/14 raw series;0 qualifying prelaunch histories,0 FX,12 missing references|
|7: actions/inactive securities|BLOCKED for real completeness|Source-driven dividend receivable/payment adapter;unresolved mergers/delistings veto admission|
|8: readiness|COMPLETE,FAIL|STRICT7/16 pass;EXPLORATORY7/17 pass|
|9: paired historical run|BLOCKED|Both resume commands fail closed;no complete admitted input bundles|
|10: reporting/checkpoint|COMPLETE for blocked outcome|This report,dual-mode readiness,master status,exact input schema and ignored checkpoint|

**128 research tests and 16 isolated paper-trial tests passed.** Original U.S.
synthetic parity passes all six categories,with current program hashes. No
authoritative matching historical five-stock trade/NAV oracle is available.
No original tests were weakened. AstraZeneca conversion,Korean genuine rebound
andTaiwan extraordinary closure tests remain passing.

All97 original compressed universes,holdings/snapshot inputs and 16 recorded
price sources match prior SHA256s. Production strategy/app source is unchanged.
No trade,purchase or new EODHD request occurred in this continuation. Public
source observations,raw prices and credentials remain outside Git.

## Classification modes and sensitivity

`STRICT_PIT` remains the default with original historically verified GICS
effective/available-date requirements. `EXPLORATORY_CURRENT_GICS` prefers
verified historical evidence,then documented current GICS with dated
corrections where available. Every approximation keeps source URL,file hash,
retrieval/as-of time,taxonomy,typed security identity and status. Current data
never become historically verified. Later-known corrections remain explicitly
retrospective. No inferred business/SIC/NAICS sector is relabeled GICS.

Coverage retains every security/country denominator:≥98% each cutoff,≥95%
each material country,and100% of admitted usable rows. No Unknown-sector
risk bucket is traded. The original eleven-sector breadth/cap/ETF rules remain.
Before monthly orders,the original rules quantify baseline versus eleven
joint sector uncertainty stresses and documented individual alternatives.
Reports include selected names,weights,caps,regimes and changes. Those
scenarios are not exhaustive historical truths or probabilities.

The 48 SEC-only universes contain128,469 confirmed security-months,2,403–2,910
equities each,and58–123-day portfolio ages. No exact-identity,current-GICS
overlay has yet been substantiated across this global set,so executable
sector coverage is0% in both modes. The static audit records this gap;actual
rank/performance sensitivity is unavailable without complete prices. Policy
approval removes a mandatory historical-GICS license,not the need for sourced
classifications. See EXPLORATORY_GICS_POLICY.md.

## New source findings

The existing provider's public S&P history has 1,005 rows. Naive September 2023
filtering produces 512 symbols; the documented creation-date safeguard removes
eight later aliases,leaving 504 symbols/500 CIKs. FI/FISV still overlaps.
FOX/FOXA,GOOG/GOOGL andNWS/NWSA include distinct share classes and remain
separate. Eleven retained rows contain approximate date markers. Prior-public
announcement timing is absent. Current membership is never substituted.

The public503-row current GICS dataset declares ODC-PDDL-1.0 and supplies
448/504 issuer-level candidate joins (88.89%). These do not verify share-class
identifiers or historical listings. Source publisher licenses/README,data
and hashes remain ignored. See US_REFERENCE_INPUTS.md for caveats and URLs.

2040 cached Korea/Taiwan exchange records yield7792 exact-ISIN candidate
security-months (6.07% globally),with 0 contradictory current listing joins
observed. Current observations remain non-historical. Ordinary shares are
not mapped to ADRs by company name. Full dated ticker/MIC/currency/unit/issuer
coverage is still absent. See HISTORICAL_LISTING_RESOLUTION.md.

IBKR's earlier connected-service baseline is range/count metadata,not a Codex
API or raw export. It reports Korea1216 bars from2021-10-12 andTaiwan842 from
2023-04-25 through 2026-10-08;Taiwan's observed history lacks the prelaunch
warm-up. No broker pilot/contract request was made. Needed:an authorized
read-only endpoint/runtime session with existing venue entitlements,or
entitled exported bars/contracts. See IBKR_ACCESS_READINESS.md for a small
sequential pilot and endpoint-specific pacing verification.

SPY's official product page exposes historical price/NAV spreadsheet links.
They were not imported as validated OHLC. NAV/performance does not replace
ATR/stop/fill data. Yahoo terms,Wikipedia historical revisions,S&P official
index information andIBKR documentation checks encountered proxy403. Existing
ECB download blockers were not retried without a runtime change. No permitted
long-history entitlement was assumed from code or a connected ChatGPT app.

The saved environment draft preserves prior settings and adds
`en.wikipedia.org`,`www.spglobal.com`,`legal.yahoo.com`,
`interactivebrokers.github.io`,plus updated continuation instructions. Review/
save and publication are needed to activate it. This does not provide IBKR
credentials/permissions or guarantee data completeness. PriorECB destinations
remain preserved. No access controls or TLS checks were bypassed.

## Remaining external requirements

| Deliverable | Required fields/coverage | Why current evidence fails |
|---|---|---|
|Sourced GICS overlays/corrections|Exact typed security identity,explicitGICS,source/hash/as-of/taxonomy;historical or current labels with approximation flags|Current U.S. issuer candidates do not provide full global/inactive security coverage|
|S&P historical membership|September 2023 initial set,dated additions/removals,alias reconciliation and prior-public source times|504 candidate symbols include overlapping aliases and lack announcement timing|
|Dated global security master|ISIN/CUSIP/SEDOL/issuer links,primary/ADR/classes,unique ticker/MIC,currency/units,effective/known intervals,inactive lines|7792 current candidates establish no historical intervals|
|Historical prices/references|RawOHLCV,separate consistentTR/adjustments,approximatelyJanuary 2021–September2026;all eligible/inactive securities,SPY+11 ETFs|Both cache sets have0 qualifying prelaunch series;all references absent|
|FX/calendars|All listing currencies;positiveUSD/major-unit rates observable at closes/opens;≤5-day age;actual venue sessions/closures|0 validatedFX tapes;full calendar/time/source audit absent|
|Corporate events/recoveries|Ex/pay/effective/known times,split/share ratios,source-based cash/stock consideration,delisting/fractional settlement|429 dividend-bearing series lack payment/entitlement metadata;material merger/delisting adapters/evidence remain unresolved|

EODHD's last known entitlement isFree with approximatelyone-year history;
its usage date is stale. No account reset or additional paid entitlement was
assumed. A larger free daily allowance alone does not solve range/mapping/FX
blockers. Supply existing authorized exports/access;no automatic purchase.

Income accounting is source-driven:earned dividend claims remain receivables
until actual payment and survive a sale. Buying after ex-date cannot earn
them. Both configurations declare the same source-verified net/gross policy.
Economic NAV,spendable cash and stock/sector attribution reconcile. Existing
TR ranking remains separate from raw-price NAV/ATR. Price-onlyFIFO lot win
statistics do not allocate dividends to closed lots. Unsupported material
merger/delisting events fail instead of disappearing through survivor filtering.
See CORPORATE_ACTION_ACCOUNTING_READINESS.md.

## Performance availability and diagnoses

| Measure | S&P500 | SPGM proxy |
|---|---|---|
|CAGR/total return|Unavailable|Unavailable|
|Drawdown/volatility/Sharpe/Sortino|Unavailable|Unavailable|
|Turnover/exposure/fees|Unavailable|Unavailable|
|Trade/stock/sector attribution|Unavailable|Unavailable|
|Annual 2023 (Oct–Dec),2024,2025,2026 (Jan–Sep)|Unavailable|Unavailable|
|All 36 monthly returns,October 2023–September 2026|Unavailable|Unavailable|

Unavailable is not zero. Machine-readable performance is null;no historical
NAV/holdings/trades were manufactured. Synthetic fixtures remain labeled and
separate. The source proxy is sampled/lagged ETF holdings,not officialMSCI
ACWIIMI membership. Current-GICS approximation would further limit any
exploratory sector attribution even after valid execution.

2023 underperformance is not established by a matching original five-stock
record;older20-stock/leadership experiments cannot prove it. For2024–25 and
2026,eligibility evidence alone does not establish momentum rank,entry/exit,
sizing or gains from international semiconductor/memory leadership. Improvement
in return,drawdown,consistency,risk-adjusted performance and preference versus
S&P500 remains undetermined. Cash/stop causal impacts require counterfactuals;
observed cash fractions and stopped-lot P&L are not causal benefits.

## Automatic continuation

Prepare ignored `historical_backtest/input_bundle_manifest.json` with both
SP500 andSPGM_PROXY evidence bundles. Both declare
`admission_mode: EXPLORATORY_CURRENT_GICS` and the same dividend convention.
Follow HISTORICAL_INPUT_BUNDLE_FORMAT.md for complete daily prior-public
membership,sector/listing records,price/FX/actions,source hashes and rights.

```bash
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.parity_harness
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.global_backtest_pipeline --mode EXPLORATORY_CURRENT_GICS --resume
```

The runner automatically admits/replays both configurations and publishes
comparison/attribution only after both succeed. Classification stresses occur
before monthly orders. No provider/broker call is made by this command. A
failed admission/replay leaves performance blocked. Mode-specific readiness
and results,classification assignments/sources,sensitivity,inventory,access
failures and final continuation checkpoint remain under ignored storage.

Last completed execution checkpoint: 65e4305;readiness 373b365;actions e668d7b.
The final report commit is discoverable with `git log -1`;completed research
commits are pushed to the same research branch.
