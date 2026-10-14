# GEMv1 manual-only operations — implementation and release runbook

**Owner's execution instruction (2026-10-13): there is NO broker integration. The owner places all orders manually once per month.**

## What is deployed vs what is verified

The GEM-only Render service hosts an authenticated, stateless operations workbench at `/gem-manual`. Its calculations are diagnostics, not certified signals or automated execution. Existing source-ingestion workers and GEM-only Neon read projections remain isolated from other services. `gem_experiment.execution_enabled` remains enforced FALSE in PostgreSQL.

Current data must be independently reconciled before any real-world trade selection is described as verified. Do not run orders based on backfilled 2025/2026 research projections. The workbench does **not** persist submissions yet; save the JSON results and imported fills externally.

## Frozen strategy rules (do not optimize or improvise)

- Effective-dated S&P 500 constituents; at least 127 price bars, nominal share price ≥$5, ADV20 ≥$10m
- SEC 10-Q revenue YoY >20%; current positive net income and either income YoY >20% or recovery from nonpositive prior-year income
- Operating margin YoY improvement >3 percentage points
- Rank qualifying stocks by trailing 63-session adjusted-close return, decreasing
- **Up to five names at 20% each**; fewer than five means the remainder stays cash. April 30, 2025 archived original selected three names and 60% gross.
- Rebalance at next session open, sells before buys; whole shares; modeled 20bps per side. Actual manual brokerage execution will have different fills/costs.
- IMPORTANT: the actual archived simulator did NOT enforce a separate positive r63 gate; the isolated `coverage_gate.py` currently does. The new `gem_monthly_signal.py` reproduces the archived gate and records the difference. Backtest-parity release still requires selecting one frozen interpretation explicitly.
- Do not import unrelated Dual Momentum workers and do not submit trades from the Render process.

## Operator flow

1. Collect S&P membership with stable IDs, S&P effective/announcement dates, a verified NYSE session calendar and independent issuer corporate-action receipts.
2. Obtain 127 verified daily completed stock bars per effective constituent and independent SEC original-filing values for six aligned quarters; check source hashes, filing timestamps, and quarterly period identity. **No missing candidate competitors may be silently excluded.**
3. If Marketstack is missing sessions, run `gem_data.market_data_patch.reconcile_prices` on source-identified nominal OHLCV observations. The adapter `gem_data.tiingo_eod_probe` can supply an alternative *only* if the owner separately has a Tiingo token/appropriate entitlement. Two independent sources agreeing is a repair candidate, **not** certified frozen adjusted-price parity.
4. Run `gem_data.gem_source_feature_verifier.recompute_full_month` from raw bars and six SEC quarter facts, then review its blocker list and provisional rank. Reconcile against the original archive by month before using on any live day.
5. If all inputs are reviewed, create an indicative `gem_data.gem_manual_ops.manual_trade_sheet`. It never contacts a broker.
6. Owner places actual orders manually in the broker. Record fills, commissions and actions in `replay_manual_events`; **only entered fills affect actual ledger shares/cash**, not intended tickets.
7. Export brokerage holdings and cash into a statement receipt, reconcile line-by-line; discrepancies remain HOLD. Keep original receipts and hash-chain reports.
8. Audit sources, monthly readiness and historical membership/actions with separate QA artifacts. No user authorization or dashboard flags can turn missing data into verified history.

## Stateless workbench and CLI

Authenticated web:
- `GET /gem-manual`
- `GET /api/gem-manual/readiness`
- `GET /api/gem-manual/mode`
- `POST /api/gem-manual/run/{verify|signal|gaps|tickets|ledger|history}`

Offline JSON tools:
```bash
python -m gem_data.gem_manual_cli verify --input sourced_month.json --out output/2026-10-source-check.json
python -m gem_data.gem_manual_cli gaps --input price_sources.json --out output/vendor-gaps.json
python -m gem_data.gem_manual_cli tickets --input ticket_inputs.json --out output/monthly-trades.json
python -m gem_data.gem_manual_cli ledger --input manual_fills.json --out output/reconciled-ledger.json
python -m gem_data.gem_manual_cli history --input claims.json --out output/historical-review.json
```
Outputs use atomic create-if-absent; never overwrite recorded audits or imported statements.

## Persisted-account preparation

The isolated Neon project now has dedicated `gem_manual_entry` and `gem_manual_statement` tables. **There are no runtime INSERT permissions granted to this workbench.** Restricted append-only credentials and safely authenticated entry/statement endpoints must be independently tested before enabling persistent manual accounting. Until then, save and preserve report JSON files; do not assume the web tool stores them.

## Track B archival source audit

`gem_data.historical_claim_builder` extracts membership entry/exit and split/dividend/spinoff claims from the *original frozen* market archive and historical trade/signal artifacts. Claims are prioritized if the affected ticker was held on the event date. `.github/workflows/gem-track-b-history.yml` is configured to produce a machine-readable issue worklist from both branches.

Primary S&P announcement starting points:
- Feb 4, 2026: CIEN addition and DAY deletion effective Feb 9: https://press.spglobal.com/2026-02-04-Ciena-Set-to-Join-S-P-500-Arrowhead-Pharmaceuticals-to-Join-S-P-MidCap-400-ADT-and-OneSpaWorld-Holdings-to-Join-S-P-SmallCap-600
- Dec 6, 2024: APO and WDAY added effective Dec 23, 2024: https://press.spglobal.com/2024-12-06-Apollo-Global-Management-and-Workday-Set-to-Join-S-P-500-Others-to-Join-S-P-MidCap-400-and-S-P-SmallCap-600

These links are **source leads, not proof that every archived member and action has been reconciled**. Historical issuer event ratios/payment dates, alternate security IDs and missed delisting consideration remain independently reviewed. Track B historical audit is separate from forward paper readiness unless it reveals a flaw in the current engine.

## Release checklist

- [x] Broker connector excluded from architecture and no automated trading routes
- [x] Manual calculation, trade-sheet and user-fill ledger modules committed
- [x] Vendor-gap inventory, optional alternate EOD adapter and provenance classification
- [x] Effective-dated membership and month-end session scheduling modules
- [x] Raw-price/SEC numeric recomputation module
- [x] Historical event worklist generator and source reconciliation ledger
- [x] Isolated Neon append-only schema created (application write permissions withheld)
- [ ] Full regression CI results confirmed passing on the deployed commit
- [ ] Full-universe 127-session price coverage with adjustment parity and complete latest SEC quarter set
- [ ] Archived month-by-month selection parity including ties and portfolio accounting
- [ ] Effective-dated membership review of material competitors
- [ ] End-to-end persistent manual-fill/statement storage enabled, tested and reconciled
- [ ] Daily source refresh, monthly report persistence, failure notification and restart recovery proven
- [ ] Manual owner approval of final trade sheet and independent paper-period QA

No hidden backfill, no manufactured vendor values, no paper-account initialization using a fictitious actual broker deposit.
