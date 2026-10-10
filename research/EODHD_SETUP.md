# MSCI ACWI IMI research — EODHD Free Plan / Codex setup

For the separate **SPGM historical ETF holdings proxy** (public SEC/Wayback
sources, zero EODHD calls), see [SPGM_PROXY_REPORT.md](SPGM_PROXY_REPORT.md).
For the strictly prior-public stock-membership construction, company-appearance
audit and five-stock strategy readiness assessment, see
[SPGM_UNIVERSE_READINESS.md](SPGM_UNIVERSE_READINESS.md). Run
`python -m research.spgm_universe` and `python -m research.spgm_universe_report`
entirely offline; monthly security-level exports stay compressed and Git-ignored.
`python -m research.spgm_sources`, `python -m research.spgm_benchmarks`, and
`python -m research.spgm_proxy` rebuild from the existing ignored cache without
network requests. Only the first two accept explicit `--fetch` for public-source
retrieval; those commands cannot access EODHD. Raw/normalized holdings stay under
`research/eodhd_output/spgm_proxy/` and must never be force-added to Git.

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

## Corporate actions, primary-market coverage and offline reports

Research-only helpers do not change the trading strategy or send orders:

- `corporate_actions.py` flags raw/adjusted close changes above 25% and
  adjustment-factor changes above 10%. Flags require review; they are not inferred
  splits. It parses verified new-shares/old-shares events, checks the event ratio
  against adjusted-price continuity, and prepares split-only OHLC. Unexplained
  jumps, mismatched events, or incomplete event history block export. A genuine
  extreme return corroborated by dated independent evidence and stable raw/adjusted
  factors retains its full price move and true range; it is never made into a split.
- EODHD `adjusted_close` contains both dividends and splits. Multiplying OHLC by
  `adjusted_close/close` does **not** produce split-only bars. Use verified event
  ratios instead. Before an ex-date, divide each raw OHLC price by the new/old
  share ratio; on the ex-date, leave that bar on its new share basis.
- EODHD volume is already split-adjusted. The helper retains it without another
  adjustment. Bars use an explicit end-date share basis; historical position,
  stop and order units must be converted to that same basis in a future simulation.
  No prepared prices are wired into existing strategy or execution code.
- Cached CSVs are revalidated and flagged without making requests. A CSV alone
  lacks request-range provenance: inspect the coverage report and calendars rather
  than assuming the cache covers an arbitrary requested period.
- `eodhd_client.py` reserves endpoint costs **before** requests, including failed
  requests, and separately caps HTTP request count. It has no retries or redirects.
  Supported endpoints are read-only. Quota responses are reduced to counters/date;
  personal account fields, tokens and authenticated URLs are not saved or printed.

Run all research tests without credentials or network, using the validation
environment below for the calendar-test dependencies:

```sh
/workspace/.venvs/eodhd-validation/bin/python -m unittest discover -s research -p 'test_*.py'
```

Endpoint costs, verified from <https://eodhd.com/financial-apis/api-limits>:
daily history, split history, exchange symbol list and search cost **1** each;
Technical API costs **5**; `/api/user` costs **0**. Query account usage before
reserving a plan. A local experiment ledger is not the provider's account-wide
daily allowance; inspect `apiRequestsDate` because old counters can survive a
midnight GMT reset until the first new request.

The Asian/corporate-action experiment uses its own ledger under the ignored
`research/eodhd_output/asia_corporate_actions/` directory. Its plan is two exchange
lists, one AZN split history, six daily histories and two free account checks:
**9 API-call units / 11 HTTP requests**, below both 12-unit and 12-request caps.
Do not rerun authenticated requests to rebuild the report. Cached exchange lists
verify identity, quote currency and ISIN before requesting local price history.

To reproduce the **offline** combined report from existing downloaded files:

```sh
python -m venv --system-site-packages /workspace/.venvs/eodhd-validation
PIP_CACHE_DIR=/workspace/.cache/pip /workspace/.venvs/eodhd-validation/bin/python -m pip install exchange-calendars==4.13.2 holidays==0.106
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache /workspace/.venvs/eodhd-validation/bin/python -m research.build_eodhd_quality_report
```

Run from the repository root. Outputs are `combined_data_quality_report.md`,
`combined_data_quality_report.json` and, only after event checks pass,
`AZN_split_only_ohlc.csv`, under the ignored experiment directory. Never commit
these outputs or downloaded market data. The report combines the earlier
eight-stock sample with six Asian primary listings and
`research/ibkr_asian_coverage_baseline.csv`. The IBKR baseline contains dates and
counts, not OHLC bars, so price-by-price agreement cannot be established from it.

The report records exchange-calendar discrepancies separately from missing data.
For Korea, the national-holiday library reconciles two holidays missing from the
exchange-calendar release; exchange-specific confirmation remains separate.
Stock-specific absent sessions and unusual adjusted-price moves are left unresolved
until independently checked. Do not fill gaps or infer corporate actions merely
to make a backtest pass.

`verified_quality_evidence.json` records independently verified information
supplied by the user, with date, exchange/security scope and provenance. The
2026-07-31 Korean returns match the supplied IBKR returns within 0.005 percentage
points and have stable adjustment factors; the report classifies them as genuine
extreme market returns. Taiwan's 2026-07-10 Typhoon Bavi closure applies to every
XTAI security, removing TSMC's false missing-session flag. Cached bars on that
closed day for other securities remain flagged rather than deleted. This report
revision makes no requests and does not refresh the previous account snapshot.

`session_filter.py` excludes only explicitly confirmed exchange closures from
derived price inputs. It preserves the original observations, records exclusion
evidence and never guesses a replacement date. Flat zero-volume bars equal to the
previous trading close are classified as consistent with carried-forward
placeholders; zero volume on an open day alone does not remove a bar.
The combined report records original and output SHA-256 hashes and writes Asian
session-filtered CSVs under the ignored `backtest_inputs/` directory. Those files
still contain provider raw prices: session filtering does not establish complete
corporate-action, FX or historical-universe readiness, and it does not change
existing strategy input paths.

### Global strategy input audit (offline)

With the 48 cached monthly universes available, run:

```bash
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
  /workspace/.venvs/eodhd-validation/bin/python -m research.spgm_strategy_audit
```

This audits historical GICS verification, ticker observations, dated listing
verification and identifier/issuer ambiguity without fetching data or importing
the strategy. Detailed CSVs and source hashes stay under ignored
`eodhd_output/spgm_proxy/strategy_audit/`. Aggregate results are documented in
[SPGM_STRATEGY_COMPLETENESS.md](SPGM_STRATEGY_COMPLETENESS.md); the read-only
strategy audit, source evaluation, acceptance thresholds and proposed price/FX
specification are in [SPGM_GLOBAL_BLOCKER_RESOLUTION.md](SPGM_GLOBAL_BLOCKER_RESOLUTION.md).

### Historical five-stock A/B continuation (offline)

The isolated engine, source-pinned synthetic parity and cache-only readiness
runner are described in [HISTORICAL_ENGINE.md](HISTORICAL_ENGINE.md) and
[HISTORICAL_INPUT_BUNDLE_FORMAT.md](HISTORICAL_INPUT_BUNDLE_FORMAT.md). Run:

```bash
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.parity_harness
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.global_backtest_pipeline --resume
```

At the verified checkpoint the result is `EXTERNALLY_BLOCKED`, with nine failed
input requirements and no historical performance figures. No authenticated
market-data request is made by either command. The pipeline verifies input
checksums, historical metadata timing, exact SEC-only daily membership and
replay validity before publishing paired outputs. Current EODHD Free history
and a stale usage date do not authorize a costed historical download.

The environment configuration draft preserves existing setup/network settings
and adds `www.ecb.europa.eu` and `data-api.ecb.europa.eu` plus these continuation
steps. Review/save and publish in environment settings to activate that draft.
Current-instance public ECB attempts failed with proxy403; the offline SDMX
parser is tested, but no archive or publication-time verification was obtained.
