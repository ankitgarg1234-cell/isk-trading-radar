# Market-wide scanner + company-name analysis patch

## Fixes

1. Removes the old 12-symbol default seed universe.
2. Loads the eligible U.S. listed-equity universe from Nasdaq Trader symbol-directory files, with SEC ticker-map fallback.
3. Rotates through the full universe continuously during the U.S. regular session.
4. Uses a lightweight first-pass price/volume/momentum screen across each universe slice, then deep-analyzes only promising names plus positions/watchlist/manual requests.
5. Exposes universe size and per-cycle prefilter counts in the live API/dashboard.
6. Manual Analyze input now accepts either ticker or company name.
7. Company-name resolver uses exchange directories, fuzzy issuer-name matching, direct ticker input, and Yahoo search fallback.

## Default scan settings

- SCAN_INTERVAL_SECONDS=120
- UNIVERSE_PREFILTER_BATCH_SIZE=120
- SCAN_BATCH_SIZE=28 (max full/deep analyses per cycle)
- UNIVERSE_DEEP_CANDIDATES=10
- DISCOVERY_DEEP_CANDIDATES=8
- PRIORITY_DEEP_LIMIT=12
- QUICK_SCAN_WORKERS=8

These are environment-overridable. The broad market scan is intentionally two-stage so thousands of stocks are not sent through SEC/news/AI calls every two minutes.

## Tests

43 passed / 0 failed on the cumulative V1 codebase after this patch.
