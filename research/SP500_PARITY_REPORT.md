# S&P 500 five-stock parity report

Checked10 October2026. **Code-level and deterministic synthetic parity PASS.
Historical performance parity is not established.** No real historical
investment results are reported by the fixture.

The authority is `dual_momentum/trial.py` and its pinned pure-function manifest.
`dual_momentum/PAPER_TRIAL_POLICY.md` identifies the isolated Top5/Top15/3.5ATR
trial. `rules.py` defines20 holdings, Top35 retention and3ATR for a different
engine. `scripts/dual_momentum_backtest_5y.py` and its75/25 leadership
experiments use that older framework. Their performance records cannot serve
as an oracle for this requested strategy. No authoritative historical
five-stock trade/NAV record covering2023–26 was located in this checkout.

The replay fixture uses500 synthetic stocks, SPY plus all11 original sector
ETFs,260 supplied synthetic sessions, four replay sessions, two selection
events and one forced stop-gap event. The independently orchestrated reference
executes the original `_stage_decision`, `_execute_pending`, `_stop_check`,
`_daily_risk_check` and mark-to-market functions. The historical engine
executes its separate scheduler/FX/local-stop/cash adapters against identical
input histories and memberships. NAV/cash tolerances are1e-8; discrete
selections and shares, trade dates, fees and holding stop states match.

| Compared requirement | Evidence | Result |
|---|---|---|
| Momentum/EMA/volatility/ATR calculation | Exact audited trial function, pinned source; known-window return and EMA qualification fixture | PASS on supplied identical histories |
| Raw/risk ranks and selected stocks | Both decision snapshots: raw ranks, selected order, quantities, allocations; Top15/lockout/cap fixture | PASS |
| Incumbent retention and lockout | Protected rank15 fixture, post-stop exclusion, final replay lockouts | PASS |
| Sector breadth/regimes | Every exposure-table boundary,89% coverage veto; replay regimes/caps | PASS |
| Position weights/cash reserve/sector cap | Exact target weights; integer floors and50% cap retained without reallocating spare cash | PASS |
| Next-open entries/exits | Reference trade audit vs independent event fills | PASS in identical U.S. calendars |
| Stop gaps/trailing state | One replay stop; gap price, close-based versus peak-based formula, nondecreasing stop | PASS |
| Cash/fees/NAV | Every replay close, all trades, insufficient-cash purchase and sell fixtures | PASS |
| Daily risk management | Replay drift review and explicit reduced-cap target fixture | PASS |
| Historical performance parity | No matching original historical five-stock record | NOT VERIFIED |

International changes are documented in `HISTORICAL_ENGINE.md`: dated calendars,
USD cash and FX signals, native OHLC/ATR stops, asynchronous execution funding,
share-representation transformations and conservative daily-data stop proceeds.
They are data/accounting adaptations, not tested against imaginary historical
live decisions. Currency/price-unit migrations, complex spin-offs and delisting
recoveries need verified adapters before affected records may pass readiness.
The preserved cash-dividend accounting limitation is disclosed. The entire
supplied-history EMA seed is deterministic; reproducing unknown Yahoo2y
download vintages cannot be claimed.

Validation at this milestone: **89 research tests passed** (71 existing plus18
new engine/metrics/parity regressions), and **16 existing paper-trial tests
passed** using an isolated in-memory database. Original live/paper source
files have no changes. Existing AstraZeneca, Korean rebound and Taiwan closure
tests still pass. No data request or real trade occurred.

Reproduce:

```bash
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.parity_harness
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m unittest discover -s research -p 'test_*.py'
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache DATABASE_URL='sqlite:///:memory:' \
 /workspace/.venvs/isk-trading-radar/bin/python -m unittest tests.test_paper_trial
```

Machine-readable fixture audit, decisions, NAV, trades, orders and action records
are under ignored `research/eodhd_output/spgm_proxy/historical_backtest/synthetic_parity/`.
They are labeled `SYNTHETIC_FIXTURE`, never used as historical strategy results.
