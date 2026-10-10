# Historical price and FX inventory

Inventory is offline. Existing cached observations and legacy staged files are unchanged. Series labels do not establish dated listing identity.

| Cache | Series |253 prelaunch bars | Adjusted/TR field | Readiness limitation |
|---|---:|---:|---|---|
| Legacy staged price cache | 539 | 0 | No explicit adjusted close in any series | Starts too late for prelaunch momentum; all12 reference series absent |
| EODHD raw cache | 14 | 0 | Separate adjusted close present | Approximately one year of history, not2021–26 |
| Verified historical FX |0|0|None|Currency-sensitive ranking/NAV/fills blocked|

The legacy539-series cache supplies at most **211** prelaunch observations versus253 required (254 for the two-close SPY regime). Its503 sector labels lack historical GICS effective/publication dates. A dated membership-change event is not evidence of public-knowledge timing. These records can support data diagnostics, not a silently shortened or survivor-biased October2023 comparison.

Raw EODHD cache span: **2025-10-09–2026-10-09**. Records after September30 2026 are retained in raw storage but cannot enter the requested result period. The separate AZN split-normalized and Taiwan session-filtered derivatives remain preserved; derivatives do not supply missing historical years, FX or sectors.

Cached independent IBKR coverage counts are metadata, not downloadable daily OHLC inputs. No verified FX price tape, complete reference ETF histories or full global historical price bundle was found. Detailed per-series counts and original-file SHA256s are stored in ignored `historical_backtest/price_inventory.csv` and `price_inventory_summary.json`.

Required acquisition remains January2021–September2026 (subject to actual listing dates), all historically eligible equities including inactive securities, SPY+11 sector ETFs, verified action history, native calendars and timestamped USD-per-local-unit FX. Do not backfill the missing2023 warm-up with current constituents or invented prices.
