# GEM 2025–2026 validation

**Final classification: Insufficient data for strict point-in-time validation.** Exact archived accounting/configuration reproduction passed. Narrowed accounts and SPY are **uncertified retrospective replays**, using archived inputs plus public October 2–9 prices. They are not certified performance or independent out-of-sample evidence.

| experiment | policy | return_pct | max_drawdown_pct | ending_nav | cagr_pct |
| --- | --- | --- | --- | --- | --- |
| A_2025 | original | 96.16 | -22.80 | 19616.33 | 96.98 |
| A_2025 | SPY | 15.78 | -17.73 | 11578.12 | 15.89 |
| B_2026_YTD | original | 73.80 | -24.92 | 17380.29 | — |
| B_2026_YTD | SPY | 13.59 | -8.54 | 11359.10 | — |
| C_continuous | original | 335.31 | -29.01 | 43531.12 | 130.01 |
| C_continuous | SPY | 32.14 | -17.73 | 13213.96 | 17.10 |

2026 ends October 9, the latest completed session before the October 11 cutoff: 194 sessions. Its return is YTD, not annualized. Continuous C has 444 sessions /645 elapsed calendar days and no capital reset. A remains a complete calendar-year return; its mechanically calculated elapsed-period CAGR is not the calendar-year return.

All three previously documented retention variants are reported, without choosing one. Original-versus-SPY comparisons use identical $10,000 initial capital, dates, whole shares, 20bps costs and ex-date cash dividends. Independent accounts first wait for a newly generated January month-end signal; SPY buys at the first session open. The continuous account carries gains and positions through January 2026.

## What is verified

* Exact equality of archived return, drawdown, rolling-best, rolling-median, trade-count and costs: +413.531% full archived return, −29.240% MDD, +88.119% rolling median, +275.543% rolling best. This older reproduction includes 2024 only because it is necessary to check the stated archive metrics, not a new strategy comparison.
* Independent daily cash, share/basis, dividend and NAV reconciliation for 15 baseline accounts; profit contributions reconcile to ending NAV less $10,000.
* 52,821 fundamental input uses audited; 52,562 match direct quarterly values in the same SEC accession with actual acceptance before the signal. All 1,638 qualifying-stock input uses pass these two checks.
* Actual signals precede baseline fills; held marks have exact-date quotes. Public quotes extend the endpoint to October 9.

## What remains incomplete

5,457 missing quarter/period input records, 189 unverified direct-quarter uses, 42 standard-tag mismatches and 28 unresolved acceptance uses among competing securities; historical membership primary lineage, missing removed-company prices, nonstandard action economics, payable dates and historical industry identifiers. Verified qualifying inputs alone do not establish correct global ranking: omitted competitors could qualify or displace them.

Public EA prices were recovered and tested separately; restoring EA alone leaves the three original outcomes unchanged. AVB's public series has an unexplained 2.793:1 vendor event; it is not silently added. Yahoo and Stooq attempts did not recover usable history for the other active-window missing names. Exact security/date/field requirements appear in `pit_data_coverage.csv` and `missing_price_windows.csv`.

## Reproduce

From this directory, install `requirements.txt`, then run:

```sh
python archive_replay.py
python extend_prices.py
python run_experiments.py
python accounting_checks.py
python partial_price_reconstruction.py
python verify_artifacts.py
```

The committed public price caches reproduce the extension. To regenerate the original-accession source audit: `python acquire_sources.py`, `python audit_sources.py`, `python acquire_missing_submissions.py`, `python audit_sources.py`, `python complete_coverage.py`, `python build_report.py`, `python verify_artifacts.py`. SEC requests are throttled; full raw SEC responses are runtime caches excluded from Git. `sec_minimal_evidence.json.gz` retains exact used accession facts/acceptance times, and manifests retain response hashes and URLs. Source reacquisition may change current response hashes; compare original-accession observations, not today's aggregate statements. No current fundamentals are backfilled into past ranks.

`signal_audit.csv` covers all qualified original rankings; `signal_audit.csv.gz` covers all observed fundamental inputs including rejected names. `stock_selection_audit.csv` lists every reconstructed member at every ranking date, including absent-price names and actual target-account choices. `signals.csv` records original and retention allocations. `trades.csv`, `trade_execution_audit.csv`, `holdings.csv`, `position_pnl.csv`, `daily_nav.csv`, and monthly/contribution files supply account detail. `position_pnl.csv` includes exited names, realized net trading P&L, unrealized P&L and separately identified dividend income; the older `holdings.csv` explicitly labels trade-only basis fields. Industry columns remain blank, not filled from today's classification. Robustness results are diagnostics using the same uncertified inputs.

Production, paper positions, orders, deployment configuration, prior research and original source engines were not modified. Only this new research directory is committed on a dedicated branch.

Ranking-gap triage identifies 943 security/date rows needing further competitor review after excluding observed, verified revenue/margin failures or nonpositive archived momentum. `ranking_gap_review.csv` preserves all 10,563 rows; `potentially_displacing_competitors.csv` narrows follow-up. This conservative triage is not full eligibility certification and does not require resolving every irrelevant missing bank margin. Regenerate with `python ranking_gap_review.py`.
