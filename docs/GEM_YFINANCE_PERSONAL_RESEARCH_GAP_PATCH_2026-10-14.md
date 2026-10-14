# GEM: Personal research fallback for Marketstack June 2026 EOD gaps

**Scope: 9 June, 10 June and 15 June 2026 only, not an approved or licensed production vendor replacement.**

Confirmed Marketstack failures (Neon diagnostics, 2026-10-14):
- 2026-06-09: missing closing price across 479 stored histories
- 2026-06-10: 473
- 2026-06-15: 369
- 481/499 stored Marketstack histories have at least one rejected vendor observation

An **opt-in, manually executed** `gem_data/gem_yfinance_gap_research.py` reads precisely those rejected date pairs, fetches Yahoo price history through the Python yfinance package, retains Yahoo Close and Adj Close separately (`auto_adjust=False`), and produces a **create-only, local, mode 0600** JSON research receipt. Up to 20 ticker symbols per call; no API key; no GEM database writes or credentials leaked; no auto-scheduling; no trades.

The private output explicitly labels all candidate bars `GAP_CANDIDATE_ONLY`, `NOT_APPROVED` and `trading_authorized=false`. Row hashes are for **normalized DataFrame values only**, not independent original HTTP response digests; Yahoo 'Close' must **not** be assumed nominal pre-split or equivalent to the GEM frozen adjusted series.

## Usage outside production

Install dependencies in a personal research Python environment, **not** the production GEM Render image:

```bash
pip install -r requirements-gem-yfinance-research.txt
# Pilot with explicit symbols:
python -m gem_data.gem_yfinance_gap_research --symbols AAPL,MSFT,SPY --output ./personal-gap-sample.json
# With a separately authorized GEM read-only Neon connection:
export GEM_READONLY_DATABASE_URL='postgresql://gem_web_readonly:...'
python -m gem_data.gem_yfinance_gap_research --from-neon --output ./batch01-private.json
# Use the returned next_cursor value to advance to the following 20 affected symbols:
python -m gem_data.gem_yfinance_gap_research --from-neon --after-symbol AAPL --output ./batch02-private.json
```

Do not check the output files into GitHub. If the output path exists, the tool refuses to overwrite it. Successful local offline tests demonstrate parsing/validation but **do not prove that Yahoo has usable prices on these dates**; actual network requests are deliberately not part of CI.

## Required review before filling GEM source data

1. Verify Yahoo's personal-use terms apply to this specific use. The yfinance README states that its Yahoo Finance API access is intended for personal use only. Do not turn this into a commercial/unattended trading API adapter without proper rights.
2. For each candidate, match historical security identity, exchange and USD currency. Alias `BRK.B -> BRK-B` and `BF.B -> BF-B` is explicit but not identity certification.
3. Obtain licensed independent price/corporate-action sources (e.g., approved IBKR historical-data gateway) to corroborate Yahoo and reconstruct **full** 127-session adjusted-price semantics, market sessions, split/dividend adjustments and r63/ADV20.
4. Persist **validated source evidence** as separate GEM append-only receipts only after that source's usage rights, point-in-time correctness and approval workflow are established. Do not replace any Marketstack raw response, mark `source_qa_status=PASS`, or release a GEM monthly selection from these research observations alone.

This is a practical diagnostic bridge while the vendor support request is outstanding; it does not replace issues #72, #77 and #105.
