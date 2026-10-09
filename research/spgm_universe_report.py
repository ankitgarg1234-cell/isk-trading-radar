"""Generate aggregate universe/readiness documentation from ignored audit data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from research.spgm_sources import DEFAULT_OUTPUT, PublicCache
from research.spgm_universe import COMPANY_QUERIES


def month_ranges(months):
    values = sorted(set(months))
    groups = []
    for month in values:
        n = int(month[:4]) * 12 + int(month[5:])
        if groups and n == groups[-1][2] + 1:
            groups[-1][1] = month
            groups[-1][2] = n
        else:
            groups.append([month, month, n])
    return "; ".join(start if start == end else start + "–" + end for start, end, _ in groups) or "none"


def render(monthly, appearances):
    counts = [r["eligible_common_equity_securities"] for r in monthly]
    company_groups = [r["estimated_unique_company_groups"] for r in monthly]
    ages = [r["source_portfolio_age_days"] for r in monthly]
    alternative = [r["latest_public_SEC_only_securities_alternative"] for r in monthly]
    workbook = [r for r in monthly if r["source_snapshot_id"].startswith("wayback")]
    by_company = defaultdict(list)
    for r in appearances:
        by_company[r["company_query"]].append(r)
    lines = ["# Point-in-time global universe audit", "",
             "**Dataset: SPGM historical ETF holdings proxy — not official MSCI ACWI IMI constituents.**",
             "Checked on 10 October 2026 (Europe/Stockholm), branch `research/eodhd-acwi-imi-setup`.", "",
             "## Readiness finding", "",
             "The holdings support a reproducible **48-date, prior-public membership study**. They do **not** support a faithful global execution of the existing five-stock sector-aware risk-adjusted momentum strategy yet. No strategy was run or modified. No EODHD or other external API requests were made in this audit.", "",
             f"Confirmed common-equity membership ranges from **{min(counts):,} to {max(counts):,} securities** per month. Estimated issuer/company groups range from **{min(company_groups):,} to {max(company_groups):,}**; exact unique-company counts remain unknown because issuer crosswalks are incomplete. Portfolio ages range from **{min(ages)} to {max(ages)} calendar days**.", "",
             f"The latest-public workbook is the selected source in **{len(workbook)} months**. Those months have only **{min(r['eligible_common_equity_securities'] for r in workbook):,}–{max(r['eligible_common_equity_securities'] for r in workbook):,} confirmed securities**, while **{min(r['provisional_unclassified_securities'] for r in workbook):,}–{max(r['provisional_unclassified_securities'] for r in workbook):,} unclassified instruments** remain separate. This is a metadata-driven coverage collapse, not evidence of mass ETF sales. Using the strict subset would materially distort global country/sector breadth and rankings.", "",
             f"A separately reported **SEC-only lagged alternative** preserves explicit stock types across all 48 dates, with **{min(alternative):,}–{max(alternative):,} securities**. It uses an older portfolio when a workbook is newer. It remains an approximation with stale membership and incomplete sectors/listings, not a silently substituted universe.", "",
             "## Construction policy", "",
             "All 21 cached portfolios enter the audit: 19 target-period observations and two earlier warm-ups. For each calendar month-end, the cutoff is **23:59:59 UTC**, retained from the prior availability report. Only source information with a known-public/availability timestamp **strictly earlier** than that cutoff can be used. This is a research cutoff; a historical exchange-close decision must use its exact earlier timestamp instead.", "",
             "Choose the latest portfolio date already public; a later publication of an older portfolio does not displace a newer portfolio. Amendments are versioned by publication time. For archive workbooks the original publication date remains blank/unknown, with capture time used as the conservative availability bound. Portfolio dates are never relabeled as release dates. The source filing, URL, raw-response hash and original row numbers remain in every derived security record.", "",
             "**Eligible means an identifiable, positive-unit common-equity holding, not a momentum-qualified or executable trade.** Public SEC `EC` rows qualify structurally. Preferred shares, derivatives and short-term investment funds do not; non-positive/invalid units or missing valid typed identifiers are excluded. Common equity can include an ADR/GDR or REIT classified as EC. No guessed primary-market conversion or ordinary-share/ADR substitution is performed.", "",
             "Workbooks lack asset-type fields. A workbook row qualifies only where an exact, valid security-identifier join finds a previously public SEC EC classification. The latest applicable public classification is used; conflicting classifications remain provisional. Other identifiable positive-unit workbook rows are **provisional unclassified instruments**, potentially including cash or derivatives, not asserted to be stocks. A ticker, SEDOL, weight or company name alone is insufficient to establish common-equity type.", "",
             "Duplicate instrument exposures within a source are collapsed for membership counting, retaining every original position row reference. Distinct share classes, ADRs and ordinary shares remain distinct securities, even when they share an issuer LEI. This audit does not introduce a new one-security-per-company strategy rule.", "",
             "Country and company-LEI metadata may be resolved through exact identifiers using only prior-public source rows, with field-level dates/row citations recorded. Original values remain separately preserved. Current constituents, current ticker masters, future filing metadata, currency and security-name guesses never fill membership or country gaps. Sector values remain unfilled.", "",
             "## Monthly membership and quality report", "",
             "`Companies est.` uses source LEIs where valid and otherwise exact normalized historical issuer-name groups. `LEI issuers` is the directly identified subset; it is not a complete company count or ultimate-parent map. Missing/ambiguous ticker counts use **only point-in-time source tickers**. Every listing venue remains unverified, including rows with a ticker. `Sector gaps` counts missing historical security-level classifications.", "",
             "| Selection month | Eligible securities | Companies est. | LEI issuers | Portfolio date | Public filing / archive bound | Age | Missing tickers | Ambiguous tickers | Sector gaps | Provisional instruments |",
             "|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|"]
    for r in monthly:
        public = r["source_publication_date"] or r["source_available_at"][:10] + " (archive bound)"
        lines.append(f"| {r['selection_month']} | {r['eligible_common_equity_securities']} | {r['estimated_unique_company_groups']} | {r['distinct_LEI_identified_issuers']} | {r['source_portfolio_date']} | {public} | {r['source_portfolio_age_days']} | {r['missing_ticker']} | {r['ambiguous_ticker']} | {r['missing_security_sector']} | {r['provisional_unclassified_securities']} |")
    lines += ["", "### Country distribution for every selection date", "",
              "Numbers are counts of confirmed securities, not portfolio weights or companies. SEC Form N-PORT Item C.5 distinguishes issuer organization country from risk/economic exposure; this cache's `invCountry` supplies organization-country information. No `invOtherCountry` values were found in the 17 cached XML files. These fields do **not** establish MSCI country of classification, primary exchange, or global revenue exposure. Offshore codes such as KY and BM remain unchanged. `XX` is retained in original observations but treated as unspecified (`UNKNOWN`), never assigned from an ISIN prefix.", "",
              "For workbooks the original country field is absent. Countries below are available only for the identifier-matched strict subset via older public SEC evidence; unmapped provisional rows are not counted as known-country equities. The apparent U.S. concentration is therefore partly a crosswalk bias, not the fund's complete geographical exposure.", "",
              "| Selection month | Country code: eligible security count |",
              "|---|---|"]
    for r in monthly:
        countries = json.loads(r["country_distribution_json"])
        lines.append("| " + r["selection_month"] + " | " + ", ".join(f"{k}:{v}" for k, v in sorted(countries.items())) + " |")
    lines += ["", "## Historically observable company audit", "",
              "The queries below use explicit name aliases observed in cached historical records, not a present-day constituent list. Names label audit results; they never create eligibility or backfill earlier membership. Absence means not observed in the selected proxy portfolio, not proof of absence from MSCI or that the issuer delisted. `Provisional` can overlap `Eligible` when a second share line is unclassified.", "",
              "| Company query | Eligible months | Observed months in latest public portfolio | Provisional months |",
              "|---|---|---|---|"]
    for company in COMPANY_QUERIES:
        rows = by_company[company]
        eligible = month_ranges(r["selection_month"] for r in rows if r["eligible"] in (True, "True"))
        observed = month_ranges(r["selection_month"] for r in rows if r["observed_in_latest_public_portfolio"] in (True, "True"))
        provisional = month_ranges(r["selection_month"] for r in rows if r["provisional"] in (True, "True"))
        lines.append(f"| {company} | {eligible} | {observed} | {provisional} |")
    lines += ["", "NVIDIA, Microsoft, Apple, Tesla, Micron and TSMC are confirmed eligible in **all 48 months**. SK Hynix is observed in all 48 but is confirmed in 36 and provisional in the 12 workbook months. The SEC-only alternative confirms SK Hynix in every month. This is an instrument-mapping gap, not a historical membership deletion.", "",
              "TSMC's confirmed observations include its U.S. ADR; primary Taiwan shares are a separate unclassified workbook line in August–September 2026. `Taiwan Semiconductor Co Ltd` is a different issuer and is explicitly excluded from the TSMC query. Multiple TSMC lines are never merged as one security, and local shares are not priced using ADR units. NVIDIA is not inferred to be eligible because it is a large constituent today.", "",
              "The June 2026 SEC portfolio, public August 28, also explicitly holds TSMC primary shares (`TW0002330008`) alongside its ADR (`US8740391003`). That primary line is available in the SEC-only alternative in August–September. The newer workbook reports a different generic Identifier plus SEDOL without an ISIN crosswalk; company-name similarity is not used to invent the missing security-ID join, so its primary line remains provisional in the latest-portfolio universe.", "",
              "`company_appearance_evidence.csv.gz` preserves every matching eligible/provisional row, all identifiers, original portfolio/publication dates, source filing/URL, and membership/classification/ticker/country evidence. `company_appearances.csv` also records the SEC-only comparison. These files allow each monthly appearance to be checked against an actual historical source.", "",
              "## Strategy readiness", "",
              "The strategy was inspected read-only in [`dual_momentum/trial.py`](../dual_momentum/trial.py), with supporting data semantics in [`dual_momentum/data.py`](../dual_momentum/data.py). The current execution harness is an S&P 500 paper trial and calls `current_sp500()`; it does not consume these global research exports. No strategy module was imported or executed by the universe builder.", "",
              "The inspected rules use 63/126/252-session returns and volatility, 0.50/0.30/0.20 risk-adjusted ranking, EMA50/EMA200, SPY relative 63-session qualification, protected raw Top-15 incumbents, a five-session lockout, and five allocations of 30/25/20/15/10% with the existing 2% reserve. They also require sector breadth with at least 90% signal coverage, sector ETF comparisons and the existing 50% sector cap, plus 3.5× Wilder ATR stops based on prior-close data. None of these rules was altered.", "",
              "| Requirement | Status | Source / approximation and remaining limitation |",
              "|---|---|---|",
              "| Prior-public proxy membership and provenance | Satisfied for research | 48 monthly reconstructions with strictly prior release/capture bounds and exact source records; no current-survivor backfill |",
              "| Actual MSCI ACWI IMI membership | Not supplied | SPGM sampling, stale holdings and non-index exposures remain; cannot present the proxy as official historical constituents |",
              "| Contemporaneous monthly membership | Approximation | Latest-public portfolios are 13–123 days old; between-observation entries/exits and exact effective dates are unknown |",
              "| Common-equity instrument types | Partial / blocker for complete global universe | SEC EC is explicit; exact-ID historical carry-forward is disclosed; 12 workbook months leave many rows provisional and introduce a strong geographic coverage bias |",
              "| Distinct issuer/company identities | Approximation | Dated source LEIs plus explicitly labeled historical-name grouping; no complete issuer/ultimate-parent crosswalk or reliable company-level duplicate policy |",
              "| Country distribution | Partial approximation | SEC issuer-organization codes and disclosed stale exact-ID joins; not MSCI risk-country assignment or verified exchange country; XX and unresolved cases stay unknown |",
              "| Security IDs | Partial | Valid ISIN/CUSIP/SEDOL retained, with duplicate audit; format/checksum validity alone does not verify issuer, listing, instrument type or the workbook generic Identifier's authority |",
              "| Historical tickers, primary listings and currency/unit basis | Blocker | Pre-April 2024 SEC-based universes have no source tickers. Later exact-ID archive lookups cover only part; exchange MICs remain unverified. ADR/local lines and ticker changes cannot be silently substituted |",
              "| Security-level historical GICS sectors | Blocker for every month | Zero complete monthly classifications. SEC asset categories and aggregate sector weights are not individual GICS. No approximate GICS mapping was applied |",
              "| Sector regime/breadth and sector concentration | Blocker | Missing sectors prevent correct grouping and the 50% cap; putting every name into Unknown or dropping the sector filter would change the strategy |",
              "| Historical sector/benchmark reference series | Not established for global test | Existing code names SPY and U.S. sector ETFs (XLK, XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLRE, XLU). Keeping these is a disclosed U.S.-benchmark approximation, not verified global sector representation; full historical inputs have not been assembled |",
              "| Prices, dividends/splits, FX and delisting outcomes | Blocker | No complete global price history was joined; the October 2022 decision needs roughly October 2021 price warm-up. Known sample corrections do not validate thousands of securities or terminal returns |",
              "| ATR, stops, calendars and execution | Blocker | Needs compatible split-only OHLC/share units, complete local sessions, lagged FX, liquidity/tradability and historical delisting/restriction handling. Positive holdings units do not establish tradability |",
              "| Existing execution integration | Not performed | Research outputs remain separate; the S&P-specific harness and its breadth checks were preserved |", "",
              "Potential GICS enrichment must retain the classification scheme, instrument/issuer IDs, effective dates, original publication/availability dates, source and reuse permissions. A dated historical GICS vendor table could address the blocker. Current sectors carried backwards would be an explicit retrospective approximation and cannot pass this point-in-time audit; SIC/NAICS or a classifier would be different taxonomies, not silently relabeled GICS. No such mapping was obtained or used here.", "",
              "For exploratory research, the SEC-only lagged alternative avoids the workbook type-coverage collapse, but cannot cure missing sectors, listings or historical price inputs. A faithful five-stock sector-aware global backtest remains **blocked**. The next work is historical security/issuer/listing and GICS crosswalks with availability dates, then complete price/FX/corporate-action inputs and unchanged-rule verification in an isolated historical harness.", "",
              "## Reproduction and local artifacts", "",
              "```sh", "# Repository root; both commands are entirely offline.",
              "PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache python -m research.spgm_universe",
              "PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache python -m research.spgm_universe_report",
              "PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache /workspace/.venvs/eodhd-validation/bin/python -m unittest discover -s research -p 'test_*.py'", "```", "",
              "Inputs are the audited `snapshots.json` and `holdings.csv` under `research/eodhd_output/spgm_proxy/`. Outputs are exclusively in ignored `point_in_time_universe/`: 48 eligible and 48 provisional compressed CSVs, monthly summary CSV/JSON, country distribution, exclusions, company appearances/evidence and an input/output hash manifest. Gzip timestamps are fixed for reproducibility. Original portfolios and their normalization are never overwritten.", "",
              "Only research source, synthetic regression tests and this aggregate report are suitable for Git. Large security-level files, downloaded source data and credentials remain excluded. No trades were executed, current constituent list fetched, sector inferred or EODHD request made.", ""]
    return "\n".join(lines)


def build(output=DEFAULT_OUTPUT):
    cache = PublicCache(output)
    out = cache.output / "point_in_time_universe"
    monthly = json.loads((out / "monthly_summary.json").read_text())
    with (out / "company_appearances.csv").open() as stream:
        appearances = list(csv.DictReader(stream))
    report = render(monthly, appearances)
    strategy = Path(__file__).resolve().parent.parent / "dual_momentum" / "trial.py"
    report += "\nStrategy source SHA-256 inspected without modification: `" + hashlib.sha256(strategy.read_bytes()).hexdigest() + "`.\n"
    (out / "readiness_report.md").write_text(report)
    readiness = {"status": "blocked_for_faithful_global_sector_aware_strategy", "selection_dates": len(monthly),
                 "satisfied": ["prior_public_proxy_availability", "source_provenance", "no_current_constituent_backfill"],
                 "approximations": ["lagged_ETF_membership", "partial_exact_ID_stock_type_carry_forward",
                                    "issuer_country_not_MSCI_risk_country", "LEI_plus_historical_name_company_estimates",
                                    "SEC_only_older_portfolio_alternative"],
                 "blockers": ["historical_security_GICS", "complete_instrument_type_and_listing_crosswalk",
                              "complete_price_FX_corporate_action_and_delisting_inputs", "global_sector_breadth_coverage",
                              "verified_exchange_calendars_and_tradability", "isolated_unchanged_rule_historical_harness"],
                 "historical_GICS_approximated": False, "strategy_executed": False, "strategy_modified": False,
                 "eodhd_requests": 0, "strategy_sha256": hashlib.sha256(strategy.read_bytes()).hexdigest()}
    (out / "readiness.json").write_text(json.dumps(readiness, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.output)
    print("Report:", str(args.output / "point_in_time_universe" / "readiness_report.md"))
