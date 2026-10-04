# One-month paper trial

Authorized on 4 October 2026. The existing single `complete_strategy` ledger is
armed by `SCORE_BAND_TRIAL_ARMED_AT`; no additional account or broker order is
created. Only an entirely unstarted ledger receives the agreed HIGH profile
(1.25% planned downside per position). Active accounts retain their frozen
profile, cash, shares, pending intents and history.

The clock begins at the first eligible market-open cycle after activation
with fresh exchange quotes and an available genuine analyst score. A missing
analyst feed or stale quotes leave the trial waiting and do not relax entry
gates. A calendar month is added using America/New_York exchange time, including
daylight-saving changes and month-end clamping. If activated on 5 October, the
trial ends on 5 November at the same New York time.

The trading rules remain deterministic >=70, analyst >=75 and entry R/R >=0.4,
with allocation targets 10/15/20/30/40%, whole shares, the initial risk limit,
later fresh-quote fills, modeled friction, one-time profit-sized cash withdrawal
and the monotonic momentum stop. The dashboard's separate existing Top-20
optimizer still uses its own rules; the trial report is `/experiments/score-bands`.

At activation, capture actual equity and the trade-count baseline. Trial ROI,
trade counts and drawdown describe this new window rather than account lifetime.
The independent benchmark is an exchange-timed Yahoo `^SP500TR` observation.
Do not infer its freshness from a database update timestamp. A missing start
quote is not backfilled later; absent or stale paired observations leave the
benchmark and excess return unavailable. Stock dividends are omitted, while
the total-return index includes them.

At the deadline, freeze the last observed book and record its valuation time.
Cancel unfilled simulated intents, preserve open shares and do not force a
liquidation. Later observations cannot alter the final snapshot. Interruptions
and report reloads neither reset the ledger nor restart the clock. A stale last
valuation must be disclosed when reviewing the result; completion is not proof
of complete market coverage or profitability.

Production was unavailable because Neon rejected connections with an account
or project quota error. The user updated the Neon project/connection on
4 October; `/health` returned HTTP 200 with connected Postgres afterward.
No database-outage workaround is included in this change. Through the updated
connection, the dashboard displayed $10,000 cash, zero paper positions and
zero manual holdings. Earlier holdings were not visible; do not imply they were
migrated or permanently deleted, and do not reconstruct them from assumptions.

The trial and financial ledgers remain in the connected persistent database.
Render's free-service availability and the rotating scanner's fresh deep
coverage limit the observations captured. The full market is not scanned at
the same instant. A month of paper results is an experiment, not evidence of a
dependable 30% monthly return.

Validation commands (standard development dependencies):

```bash
python3 -m pytest tests/test_score_band_experiment.py \
  tests/test_paper_month_trial.py tests/test_paper_balances.py \
  tests/test_webapp.py -q
```

The new tests cover activation gating, profile and ledger preservation,
one-month DST/calendar boundaries, next-quote whole-share fills, benchmark
freshness/missing-start handling, baseline-equity accounting, persistent reloads
and deadline freeze without future fills or forced sales.

Verification: 52 execution, trial and balance tests passed. The broader run
passed 89 tests and failed eight existing dashboard tests; the unchanged base
reproduced the same eight failures (37 dashboard tests passed). No new dashboard
test regression was observed.

Deployment: merge only the seven trial files, preserving the database settings.
Set `SCORE_BAND_TRIAL_ARMED_AT` to the authorized UTC activation timestamp using
a merged environment update. Verify the deployed commit, `/health`, and the
trial report before describing the trial as armed. Sunday activation remains
waiting for fresh inputs; it does not count as the start of measured trading.
