# Score-band historical audit and event replay

The current archive cannot produce a valid historical return for the complete
agreed strategy. `scripts/score_band_historical.py` finishes a reproducible data
audit and supports checkpointed execution-mechanics replay. It does **not**
certify a full-market strategy backtest. Production accounts, broker orders,
the production database and deployment configuration are not accessed.

## Frozen strategy

The historical protocol uses one independent $10,000 account with the HIGH
profile: 1.25% planned downside per position. This is a historical test start,
not a reset of the existing live paper account.

All entries require deterministic score >=70, analyst score >=75 and entry
R/R >=0.4. The shared paper engine also retains its existing liquidity, quality,
confidence, negative-news, price, momentum and entry-location gates.

| Deterministic score | Target portfolio allocation |
| --- | ---: |
| 70 to below 75 | 10% |
| 75 to below 80 | 15% |
| 80 to below 85 | 20% |
| 85 to below 90 | 30% |
| 90 to 100 | 40% |

These are position targets, constrained by downside risk, available cash, fees
and whole shares. Higher scores receive cash priority. Cash can remain when
eligible entries are absent or position/risk limits bind.

- Preserve the approved pullback or breakout entry and no-chase rules.
- Breakout uses the preceding 20 completed daily closes plus 0.1 ATR. Running
  daily bars cannot set this anchor.
- A signal fills at a later fresh quote, with the original ten-minute BUY
  expiry. Fill-time entry, target, stop and R/R checks remain active.
- Model 10 bps fees and 5 bps adverse slippage on each side.
- Preserve the initial stop and the fixed target. At the base target, sell a
  one-time profit-sized cash amount rounded up to whole shares while retaining
  at least one share. This withdrawal differs from realizing all position gain.
- After withdrawal, trail the peak by 2 ATR when price >=EMA20 and RSI >=50,
  otherwise 1 ATR. Never lower the previous stop. Exit the remaining position
  through the paper engine when the stop is reached.
- Stock dividends remain omitted to reproduce the frozen paper model. The
  benchmark is S&P 500 total return in USD with dividends reinvested; this
  difference must accompany any eventual comparison.

## Run and resume

The audit needs only Python 3.12 and the committed staged gzip files. Its
imports do not load the production database or request provider credentials.
Run from the repository root:

```bash
python3 scripts/score_band_historical.py \
  --start 2024-01-01 --end 2025-12-31 \
  --checkpoint backtests/checkpoints/history-2024-2025.sqlite \
  --output backtests/results/score_bands_2024_2025.json \
  --html backtests/results/score_bands_2024_2025.html
```

Reissue the identical command after an interruption. Whole monthly chunks
commit atomically to SQLite WAL. Already committed chunks are reused. A bounded
invocation can add `--max-new-chunks 1`; omit it on resume to finish all remaining
chunks. For a one-year audit, use `--start 2025-01-01 --end 2025-12-31` and a
different checkpoint and output path.

Inputs, strategy settings, date range and scoring/execution source files are
hashed into the checkpoint protocol. Changed inputs or code require a new
checkpoint path. A mismatch is reported rather than overwriting the earlier
result or resetting the account. Provider acquisition is separate from offline
simulation, so outages cannot interrupt an already staged run.

Output status distinguishes progress from evidence:

| Status | Meaning |
| --- | --- |
| `paused` | Bounded run stopped; resume the same checkpoint. |
| `completed_with_data_gaps` | Audit/event processing finished; no strategy ROI is certified. |
| `completed_mechanics_only` | Event sequence checks passed; source/derivation validation is still incomplete. |
| `needs_attention` | Input, parsing or checkpoint error; previous checkpoints/results are preserved. |

Successful audit completion exits 0 even with explicit data gaps. An operational
error exits 2 and writes a separate `.error.json`. These distinctions prevent a
retry loop from treating unavailable historical evidence as a transient outage.
No implementation can guarantee that every process runs without an interruption;
this runner preserves completed work and reports why a result is unavailable.

## Current 2024–2025 evidence

The staged archive contains 539 price histories out of 555 historical S&P
symbols, 507 fundamental symbols and 125,709 SEC fact rows. There is no archived
analyst history or intraday quote sequence. The audit covers 24 months and 502
expected exchange sessions, including the January 9, 2025 closure. No benchmark
session is missing.

| Year | Complete strategy return | S&P 500 total return |
| --- | --- | ---: |
| 2024 | Unavailable | +25.02% |
| 2025 | Unavailable | +17.88% |

Benchmark formula: `100 * (year_end_close / previous_year_end_close - 1)`.
The cached `^SP500TR` source levels are 10,327.830078125 on 2023-12-29,
12,911.8203125 on 2024-12-31 and 15,220.4501953125 on 2025-12-31. Starting at the
first trading day's close would incorrectly omit that day's return. The
machine-readable result records the input and source-code hashes.

The audit identifies 2,373 distinct SEC accessions accepted after session close
or on closed days, 60 derived-quarter rows with unsupported period spans and
5,068 historical constituent-days without price files. These are diagnostics,
not a statement that all such filings caused a trade or that all remaining
fundamental derivations are correct. The derived-quarter diagnostic does not
exhaustively validate source dependencies.

Missing cached symbols: ANSS, CDAY, CMA, CTRA, CTLT, DAY, DFS, HES, HOLX, IPG,
JNPR, K, MRO, PXD, SATS and WBA. They are reported rather than silently dropping
them and advertising the surviving sample as the entire market.

The old daily walk-forward runner is not reused: its same-filing-date selection
can precede SEC acceptance, its split handling can adjust already-adjusted OHLC
twice, and it books next-day transactions while processing the previous day.
Using daily next-open fills would also alter this strategy's ten-minute expiry.

## Historical observation archive contract

`--archive /absolute/path/archive.jsonl` enables mechanics replay after the cache
audit. Keep the file immutable. The first line is a manifest with:

```json
{
  "start": "2024-01-01",
  "end": "2025-12-31",
  "universe": "historical_US_equities",
  "price_basis": "as_traded",
  "includes_delisted": true,
  "coverage_complete": true,
  "publication_times_verified": true,
  "expected_valuation_dates": ["2024-01-02"]
}
```

The example date list is abbreviated; a real complete archive needs every
expected session. Manifest assertions are not independent verification and
cannot unlock an investment return in this version.

Subsequent lines are strictly increasing UTC event times, grouped by polling
time. A `poll` contains `event_at`, `market_open` and `records`. Each record
contains the raw `bundle` accepted by `score_bundle`, `evidence` and
`fundamental_facts`. Evidence must cover `analyst`, `fundamentals`, `news`,
`universe` and `price`, with a source, explicit UTC `available_at` and
`availability_basis: "verified_publication"`. Month/quarter labels are not
publication timestamps. The bundle's exchange quote time is
`data_sources.price.quote_asof`; it must be fresh and no later than the event.
Daily and sector bars require ordered, unique dates and `available_at` times
not later than the quote. Financial facts require contemporaneous
`accepted_at`; derived facts also require source accession dependencies.

`valuation` events contain `event_at` and `marks`, keyed by held symbol, each
with `price` and `quote_asof`. Marks must be from the session close or later,
fresh, on the same exchange date, and present for every held symbol. The
verified 2024/2025 calendar supports holidays, early closes and daylight saving.

The current mechanics adapter rejects externally derived thesis, strategic and
promotion overrides without audited lineage. It recomputes deterministic and
analyst scores from raw bundle inputs instead of trusting archived final
scores. Processing uses the same single-account `advance()` engine. A bad
batch is quarantined atomically and makes performance unavailable; errors are
not a license to publish a shortened or selectively filtered return.

## Remaining work before a complete strategy return

1. Acquire genuine dated analyst counts/targets with verified original
   availability and revision history, and bind calculated metrics to their
   archived sources. Today's values cannot populate a historical snapshot.
2. Stage as-traded intraday prices/volume and complete news history at a cadence
   that reproduces the polling and ten-minute entry window.
3. Stage historical full U.S. eligibility, sector classifications and inactive
   securities. Current classifications or a current constituent list cannot
   substitute for these records.
4. Integrate and independently verify splits, spinoffs, merger/delisting cash
   proceeds and position/stop/share adjustments against the as-traded price
   basis. Unsupported corporate-action events currently reject explicitly.
5. Audit metric derivation, full input coverage and daily closing marks; then
   implement a certification path for annual ROI, excess return, drawdown,
   cash exposure, trade counts, costs and monthly target frequency. This version
   intentionally keeps `performance_valid` false even for a mechanics-complete
   archive; the audited-source integration is not yet implemented.

These are evidence and implementation prerequisites. Merely supplying a header
that says "complete" does not satisfy them. The 2024–2025 rules were developed
after these years, and earlier experiments used the same history. Even after
removing future inputs, these years are retrospective validation rather than
an untouched out-of-sample test. No 30% monthly return or S&P outperformance is
established by this audit.

## Verification

```bash
python3 -m unittest discover -s tests -p test_score_band_historical.py -q
```

33 integrity tests passed on 2026-10-04. They cover changed-input refusal,
transaction rollback, future-input rejection, score recomputation, later-quote
fills, whole shares, pause/resume equality, prefix invariance under future-data
changes, invalid-batch quarantine, partial-year return refusal, split-basis
rejection, incomplete-archive refusal, holiday/early-close valuations and
pre-close mark rejection. Synthetic test fixtures are not investment evidence.

The complete cached-data audit and the one-month-then-resumed audit produced
byte-identical JSON results, with result hash
`67d5152148844eda07011b5c78c1c8ee38717876f60e38ec0980db881fdefd58`.
The separate one-year 2025 audit matches the 2025 annual row of the two-year run.
Checkpoint files are local working data, not production database records. Keep
the staged gzip inputs available to reproduce the report.

## Source references

- Source data: `backtests/staged/wf3_prices.json.gz` and
  `backtests/staged/wf3_valuein_fundamentals.json.gz`, SHA-256 in the frozen result.
- [NYSE 2024–2026 holidays and early closes](https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx).
- [NYSE January 9, 2025 closure](https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx).
- [First Trust 2025 S&P 500 recap](https://www.ftportfolios.com/Commentary/EconomicResearch/2026/1/8/the-sp-500-index-2025-recap),
  January 8, 2026: corroborates the cached benchmark at its published rounding,
  25.0% for 2024 and 17.9% for 2025; exact figures above are our calculations
  from the cached index levels.
