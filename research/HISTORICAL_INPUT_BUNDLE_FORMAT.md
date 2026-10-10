# Historical input admission and exact continuation checkpoint

The runner is cache-only and automatically executes both research configurations
once complete historical inputs pass admission. It never buys data or calls a
broker. Default command:

```bash
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.parity_harness
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
 /workspace/.venvs/eodhd-validation/bin/python -m research.global_backtest_pipeline --resume
```

At the current checkpoint the command returns `EXTERNALLY_BLOCKED` and a null
performance comparison. The missing fields/datasets are identified in
`HISTORICAL_DATA_BLOCKERS.md`, not fabricated from synthetic fixtures.

## Manifest and evidence

Put `input_bundle_manifest.json` under ignored
`research/eodhd_output/spgm_proxy/historical_backtest/`. It contains
`configurations`, with exactly `SP500` and `SPGM_PROXY`. Each entry has `file`
(relative bundle JSON path) and `sha256`. Evidence paths must remain under
ignored research storage, and all supplied checksums are verified.

Each bundle has:

- `data_kind: HISTORICAL_INPUT`, matching `configuration`.
- `start: 2023-10-01`, `end: 2026-09-30`, `initial_capital: 10000`.
- `dataset_label: SPGM HISTORICAL ETF HOLDINGS PROXY` for the global bundle.
- `reference_symbols`: SPY followed by XLK,XLC,XLY,XLP,XLE,XLF,XLV,XLI,XLB,
  XLRE,XLU in the original trial's order.
- Documented `rights_permitted`, `action_coverage_verified`,
  `calendar_coverage_verified`, `adjustment_vintages_verified`,
  `complex_actions_resolved`, `missing_security_sensitivity_assessed` objects.
  Every object requires `source_url`, `evidence_file`, `sha256`; a boolean
  `ready: true` or license flag is insufficient. Evidence must substantiate the
  assertion, not simply repeat its name. Do not include credential values.

## Membership and metadata

`memberships` supplies a snapshot for **every** actual XNYS reference decision
timestamp from September29 2023 through September30 2026. The clock is16:20
America/New_York on actual sessions, including early-close days; UTC offsets
follow DST. The initial prelaunch snapshot is followed by actual October2
valuation/fill events, not an invented October1 Sunday session.

Each snapshot contains `decision_at`, `members`, and global
`source_snapshot_id`. Members retain `instrument_key`, `symbol`, `issuer_id`,
`name`, `country`, `sector`, `sector_scheme: GICS`, `exchange_mic`, `currency`,
the original portfolio/publication/security-ID evidence and source filing.
Required admission fields:

- `membership_available_at`, `membership_source_url` before the cutoff.
- `sector_verification: historically_verified`, `sector_source_url`,
  `sector_available_at`, `sector_effective_from`, optional `sector_effective_to`.
- Equivalent `listing_verification`, `listing_source_url`,
  `listing_available_at`, `listing_effective_from`, optional `listing_effective_to`.
- Resolved `issuer_id`; no contradictory `identifier_ambiguity`.

Effective intervals are distinct from first-known/public times. Current,
inferred, undated, expired and future evidence fails. Security/listing symbols
must be unique; share classes/ADRs remain separate securities. For the global
bundle, **every daily member set** is checked against the actual latest
prior-public SEC portfolio, including month-end frozen sources. Silently dropping
unresolved international stocks or adding current survivors fails admission.
The present loader is stricter than the98% minimum: every used member needs
verified sectors/listings. This preserves faithful grouping and avoids an
Unknown-sector risk bucket; it never weakens original sector coverage rules.

## Market data

`prices`: each row includes `symbol`, `mic`, ISO major-unit `currency`, `source`,
`price_scale` (default1), `open_at`, `close_at`, `available_at`, and `bar`:
`date`, `open`, `high`, `low`, `close`, `total_return_close`, `volume`.
Use native session dates and timezone-aware timestamps; TR is a coherent fixed
index basis, separately accounting for splits/dividends. OHLC/action coordinate
must remain compatible. The engine rejects wrong-calendar bars, duplicates,
invalid OHLC, missing intermediate sessions and incomplete used signal histories.
The source history/EMA seed convention must be documented and frozen.

`calendars`: mapping MIC→rows with `date`, `open_at`, `close_at`. Include all
warm-up sessions and the first subsequent opening needed for scheduling. Match
actual holidays, half days and independently verified extraordinary closures.
Do not fill absent actual bars with manufactured flat prices.

`fx`: `currency`, observation `at`, `available_at`, `usd_per_unit`, `source`.
Rates must be positive, already observable at the relevant close/open and no
more than five calendar days old. USD/USD=1 is the identity. ECB reference
dates alone do not establish publication/open-time availability; the separate
parser labels such candidates unverified and never admits them automatically.

`share_actions`: `symbol`, `effective_at`, `available_at`,
`new_shares_per_old`, `source`. Ratios must be known by effectiveness. Complex
events must be independently resolved; unsupported currency/unit migrations
or fractional cash-in-lieu cannot be guessed. Preserve AZN normalization,
genuine Korean rebound returns and the confirmed Taiwan closure exclusions.

## Execution, outputs and remaining limitations

Admission verifies metadata and source timing; the actual replay then enforces
original formulas, full-universe≥95% signal coverage,450 valid signals,
original sector≥90% coverage, reference histories, executable price/FX events,
position marks, and reconciled attribution. Identical dates, $10,000 and
SPY/sector references apply to both configurations. Missing histories do not
authorize dropping the requested2023 interval. The global SEC proxy is
explicitly sampled/stale, never MSCI membership.

After **both** configurations succeed, ignored `results/` receives daily NAV,
positions, decisions/scores/ranks/weights, orders, trades/stops, actions and
`performance_comparison.json`; `final_report.md` contains comparison and
monthly/annual tables. All output kinds are explicit. Synthetic results stay
in `synthetic_parity/`, and cannot be imported as historical input.

Stop/cash counterfactual impacts remain unknown without additional controlled
simulations; stopped-lot P&L and idle-cash fractions are reported with correct
labels. Original cash-dividend-accounting limitations, native-session windows
and conservative foreign stop-proceeds timing remain disclosed. No historical
performance-parity claim is made without an original matching five-stock record.

Exact next action: provide/import rights-permitted historical GICS/listing,
S&P membership and long-history price/FX/action evidence, assemble these bundles,
refresh source-matched parity, then run `--resume`. It automatically proceeds
to paired replay and reproducible metrics when the requirements pass. Current
EODHD Free and a stale account usage date do not authorize costed requests.

Independent ECB research is additionally blocked by proxy403 for
`www.ecb.europa.eu` and `data-api.ecb.europa.eu`. Those domains and continuation
instructions were added to the saved environment draft, preserving prior
network/start settings. The draft requires review/save and publication to
activate; saving it did not change the observed running network. After that,
verify ECB automated research/reuse terms before fetching its public SDMX
reference archive. Publication timing, TWD/other uncovered currencies and
executable FX remain separate validation requirements.
