# GEM autonomous research and production-readiness controller

## Scope and release contract (2026-10-14)

This code is deployed ONLY to the isolated GEM Render branch `draft/gem-standalone-render-20261012`, preserving frozen strategy SHA `d59b93d3d9a87d582045b4ae71ff9a6f696a48be` and the unrelated Paper Model. It is **not** a live trading system. No approval or signing authority is granted to GEM's source collectors.

## Unattended bot cycle (15 minutes)

`gem_data.gem_research_robot.run_once` now:
1. Reads all six source states and records a six-way diagnostic.
2. Tries a bounded Marketstack retry only when reserveable without violating the existing October 1,000-request cap.
3. Performs five or fewer existing Marketstack receipt integrity audits (raw SHA/OHLC only, no price approval).
4. Performs two or fewer SEC original-pair fact audits if the existing SEC QA worker is enabled; candidate completeness is not certification.
5. Independently reads source, price and release ledger evidence, checks frozen strategy, SHADOW mode, all six source approvals, 503-history price parity, SEC evidence, independent QA, approved monthly ranking, 20 distinct prospective shadow sessions and isolated broker controls. Writes an immutable `gem-release-readiness-v1-*` probe with the precise failed gate and next responsible action; release never turns the broker on.
6. Dashboard `/api/gem-portfolio/robot` and `/api/gem-portfolio/autonomous-readiness` show recorded release conditions and next actions. No GET request performs provider calls or database writes.

The existing self-contained SEC, Marketstack and official public source workers continue with their opt-in flags. The new robot can report a partial failure without falsely switching the release status to PASS.

## Explicitly opted-in Yahoo personal-research worker

`gem_data.gem_yahoo_auto_research.research_batch` requires all:
- `GEM_YFINANCE_PERSONAL_RESEARCH_OPT_IN=yes`
- `GEM_YFINANCE_PERSONAL_USE_ACK=yes`
- Restricted `GEM_READONLY_DATABASE_URL` and `GEM_INGEST_DATABASE_URL` roles.

It reads ONLY original Marketstack rows rejected on 2026-06-09, 2026-06-10 and 2026-06-15 with reason `missing or invalid vendor field: close`. It fetches 2 tickers per four-minute cycle (max 5 possible) with `yfinance` `auto_adjust=False`, USD + OHLC + action checks and known share-class aliases. Requests are reserved before any Yahoo call; a ticker is attempted at most once on a UTC day, twice in total. Provider outages or rate limiting cause holds/backoff; no infinite fetch loops.

Valid normalized Yahoo bars produce append-only GEM source receipts:
- `provider=YFINANCE_PERSONAL_RESEARCH`
- `coverage_status=UNKNOWN`
- `research_validation=GAP_CANDIDATE_ONLY`
- `source_qa_status=PENDING_PERSONAL_RESEARCH`
- `raw_http_response_sha256=null`
- `trading_approved=false`

There are **no Marketstack updates**, adjustments reconstructed from Yahoo alone, or any QA/source approvals. Provenance hashes are of normalized Yahoo DataFrame rows, *not* raw HTTP bytes. This distinction is deliberately surfaced in the dashboard.

The Yahoo/yfinance project states its Yahoo API use is for personal use only. This research workflow must be deactivated if the purpose/use becomes commercial or violates Yahoo terms. It is NOT an independently licensed production source. Production OHLCV/adjusted-close parity requires source corrections or an authorized second provider and separate reviewer signoff.

## Acceptance tests

Offline CI: `tests/test_gem_autonomous_release.py`, `tests/test_gem_yahoo_auto_research.py` plus existing Marketstack, SEC, source-gate and portfolio routing tests. The tests ensure:
- No vendor calls without explicit opt-in, no repeated requests per reserved ticker/day, bounded batches and no order placement.
- Six source gates or unrelated HTTP status cannot authorize trading.
- Even apparently successful source labels require independent review, full-universe/monthly evidence and prospective shadow; even all research gates passing cannot unlock an unimplemented broker.
- Every route is authenticated, source-only, and fails closed when the isolated database is unavailable.

## Real trading release is a different approval

GEM Render `/health` must continue to report `READ_ONLY` and `trading_enabled=false`. The autonomous gate never changes the `gem_experiment.execution_enabled` column or writes `gem_signal` / `gem_qa_review` / broker tables.

Before a separate execution service can be designed/activated: verify original-source adjusted-price parity for all eligible competitors; resolve SEC fact ambiguity; obtain authorized member/economic action inputs; reconcile benchmark/calendar; certify source evidence by an independent identity with expiry and code/evidence SHA; freeze and approve a monthly rank; run a prospective month-end+20-session paper trial and failure drills; install broker-specific risk controls and obtain explicit user authorization.

**Do not lower source quality gates to make a bot print GO.**


## Python-verified machine stages and broker-independent data comparison

The autonomous controller now explicitly lists ten **narrow Python machine checks** in the dashboard. Six can already PASS from source evidence: current ticker/CIK crosscheck, original Marketstack storage hashes/OHLC, original SEC ZIP member hashes, SEC corporate event discovery coverage, official NYSE schedule acquisition, and official SPY distribution schedule acquisition. These stages are materially different from independent source/adjustment certification and trade release; they must not be conflated.

The optional `gem_data/gem_ibkr_gap_crosscheck.py` makes GET requests **only** to the documented IBKR Web API historical-data endpoint, not orders. It checks the June 9, 10 and 15 Yahoo candidate dates against genuine IBKR trades (price geometry and volume) and writes append-only `gem-ibkr-independent-price-check-*` machine comparison probes. Agreements, discrepancies, absence, and source-authentication failures remain independently visible and never modify Marketstack originals. At most two symbols per 15-minute bot cycle; requests are reserved atomically, at most one per symbol per UTC day and two attempts overall, to prevent an unauthorized/expired session from burning API quotas. IBKR's current API limits historical requests to 50/min (Sep 2026); this bot stays well under them.

**Requires separate IBKR Web API credentials/entitlement on Render**. The user's IBKR connection inside ChatGPT does not expose its session to Render/Python. Keep this feature disabled unless the account holder has reviewed entitlements and configured the following encrypted Render environment variables:

- `GEM_IBKR_HISTORICAL_READONLY_ENABLED=yes` (default absent/disabled)
- `GEM_IBKR_READONLY_BEARER=<valid IBKR authorized SSO token>` (do not commit or log this)
- `GEM_IBKR_CONID_MAP_JSON=<explicit operator-approved symbol-to-US-stock-contract-id mapping>`

The fixed HTTPS endpoint is `https://api.ibkr.com/v1/api/iserver/marketdata/history`. The adapter rejects unexpected sources, extended-hours data, duplicate sessions, malformed OHLC/volume, missing histories, and USD-contract identity ambiguity. It does not establish that the IBKR account is entitled for automated non-display trading use, that Yahoo is licensed as a production feed, or that IBKR/Yahoo have frozen-vendor adjusted-close parity. All of those remain separate approval requirements.

The verified connector-only pilot identified official IBKR US stock contracts AAPL `265598` and SPY `756733`, returning daily histories for June 9/10/15, 2026; the autonomous service does not inherit that account connection and no SSO token has been supplied to Render.

The independent verification issue `#105` remains the authoritative tracking record. No evidence in this doc authorizes a real-money order.
