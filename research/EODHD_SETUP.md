# MSCI ACWI IMI research — EODHD Free Plan / Codex setup

This is an isolated **data-coverage probe**, not the three-year ACWI IMI backtest.
It does not modify `dual_momentum/trial.py`, order logic or existing paper trading.
Source branch: `research/eodhd-acwi-imi-setup`, created from `dual-momentum-dashboard`.

## Connect the Codex Cloud environment (user action)

1. Open **Settings > Codex Cloud > Environments**, then create or edit the environment.
2. Select the GitHub repository `ankitgarg1234-cell/isk-trading-radar`.
3. Enable agent internet access with the additional allowed domain **`eodhd.com`**.
4. Under **Network secrets**, create key **`EODHD_API_TOKEN`** with the API key value from
   your EODHD dashboard, restricted to allowed domain **`eodhd.com`**.
   EODHD authenticates using the HTTPS `api_token` query parameter. Codex's proxy
   substitutes the network-secret placeholder for HTTPS calls to permitted domains.
   If secret substitution fails in your environment, have Codex inspect its
   *secret configuration without ever printing the token*.
5. Save and **Publish** (or **Republish**) your cloud environment. New tasks use
   the updated environment; existing tasks keep their prior environment.
6. Start a Codex Cloud task in that environment, check out branch
   `research/eodhd-acwi-imi-setup`, and run the commands below.

**Never paste your key into a Codex task prompt, issue, notebook or GitHub file.**
The repository is public, so keep API tokens and downloaded data out of commits.

## Probe commands

No secret or internet needed for these first two commands:

```sh
python -m unittest discover -s research -p 'test_eodhd_probe.py'
python research/eodhd_probe.py
```

After saving the secret in Codex and enabling `eodhd.com`:

```sh
python research/eodhd_probe.py --execute --limit 8 --daily-cap 15
```

The script makes at most eight new requests, unless some tickers were already
cached. It reserves each call *before* the request so errors consume the
script's own safety allowance. The free account has 20/day; keep a margin
for other calls. Requests sent outside this script are not in its ledger.
It stops at 15/day locally by default. No retries, no parallelization.

Output stays under `research/eodhd_output/`, which is Git-ignored:
daily stock CSVs, `coverage_report.json` and `daily_request_ledger.json`.

## Coverage limits and next research steps

The sample includes German and UK local listings plus U.S. primary listings
and ADRs. **ADRs are not substitutes for primary-line price/currency data in a
final global backtest.** Korea, Taiwan, Japan, Sweden and other markets require
verifying EODHD canonical exchange codes and ticker mappings first (using
EODHD search/exchange APIs, which also consume the quota). Do not guess codes
or silently map multiple countries to a U.S. ADR.

EODHD Free is limited to approximately one year of history; this **cannot**
test October 2023–September 2026 using 252-day momentum and EMA200. Even a
paid historical price API does not supply point-in-time **MSCI ACWI IMI**
membership, security IDs, historic GICS sectors or all fundamental inputs.

For a legitimate three-year strategy test, obtain historical membership and
classification records separately; retrieve data back to at least September
2022; handle primary-exchange calendars, FX, dividends, split-adjusted OHLC,
delistings and look-ahead bias. Note that EODHD's `adjusted_close` is a
total-return-style data field for momentum, but raw daily OHLC cannot
automatically be mixed with adjusted closes for ATR/stop calculations.

Do not run or present a three-year strategy result until the backtest input
checks and selection-rule match to the original SPY results have passed.

Official docs: https://eodhd.com/financial-apis/api-for-historical-data-and-volumes
Codex environments: https://learn.chatgpt.com/docs/environments/cloud-environments
