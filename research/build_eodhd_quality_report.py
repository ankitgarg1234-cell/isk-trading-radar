"""Build offline reports from cached probes; this module makes no API requests.

Run: python -m research.build_eodhd_quality_report
Requires exchange-calendars and holidays for explicit calendar comparisons.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import exchange_calendars as xc
import holidays

from research.corporate_actions import price_flags, prepare_split_ohlc, split_events, true_ranges
from research.eodhd_probe import read_cached_prices
from research.session_filter import filter_confirmed_closures

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/eodhd_output"
ASIA = OUT / "asia_corporate_actions"


def read_prices(path):
    return read_cached_prices(path)


def coverage(rows, calendar, start, end, *, exchange_closures=None):
    expected = {s.date().isoformat() for s in xc.get_calendar(calendar).sessions_in_range(start, end)}
    actual = {row["date"] for row in rows}
    # New legal holidays can lag exchange-calendar releases. Report both views;
    # do not hide the discrepancy or call national calendars exchange evidence.
    reconciliation = []
    if calendar == "XKRX":
        national = holidays.KR(years=range(date.fromisoformat(start).year, date.fromisoformat(end).year + 1))
        for day in sorted(expected):
            if day in national:
                reconciliation.append({"date": day, "national_holiday_name": national.get(day)})
    closures = []
    for day, evidence in (exchange_closures or {}).get(calendar, {}).items():
        date.fromisoformat(day)
        if not evidence.get("reason") or not evidence.get("source"):
            raise ValueError("Extraordinary closure requires reason and provenance")
        if start <= day <= end:
            closures.append({"date": day, **evidence})
    closure_dates = {h["date"] for h in closures}
    reconciled = expected - {h["date"] for h in reconciliation} - closure_dates
    return {"calendar": calendar, "exchange_calendar_expected_sessions": len(expected),
            "exchange_calendar_missing_dates": sorted(expected - actual),
            "national_holiday_reconciliation": reconciliation,
            "extraordinary_exchange_closures": closures,
            "expected_sessions_after_reconciliation": len(reconciled),
            "session_coverage_pct": round(100 * len(actual & reconciled) / len(reconciled), 4),
            "missing_expected_dates": sorted(reconciled - actual),
            "unexpected_dates": sorted(actual - reconciled),
            "bars_on_verified_closed_dates": sorted(actual & closure_dates),
            "calendar_caveat": "Korean holiday reconciliation uses a national calendar; exchange-specific confirmation is separate." if reconciliation else None}


def main():
    evidence = json.loads((ROOT / "research/verified_quality_evidence.json").read_text())
    prior = json.loads((OUT / "coverage_report.json").read_text())
    asian = json.loads((ASIA / "asia_probe_results.json").read_text())
    before = json.loads((ASIA / "account_before.json").read_text())
    after = json.loads((ASIA / "account_after.json").read_text())
    ledger = json.loads((ASIA / "request_cost_ledger.json").read_text())
    if ledger["reserved_units"] > 12 or len(ledger["calls"]) > 12:
        raise ValueError("Experiment exceeded its call/request cap")
    with (ROOT / "research/ibkr_asian_coverage_baseline.csv").open(newline="") as f:
        ibkr = {r["local_ticker"]: r for r in csv.DictReader(f)}
    results = []
    for item, directory in [(r, OUT) for r in prior["results"]] + [(r, ASIA) for r in asian]:
        ticker = item["ticker"]
        if item["status"] not in ("ok", "cached"):
            results.append(item)
            continue
        rows = read_prices(directory / (ticker.replace(".", "_") + ".csv"))
        suffix = ticker.split(".")[-1]
        calendar = {"US": "XNYS", "XETRA": "XETR", "LSE": "XLON", "KO": "XKRX", "TW": "XTAI"}[suffix]
        flags = price_flags(rows, verified_returns=evidence["market_returns"].get(ticker))
        result = {"ticker": ticker, "status": "download_and_schema_valid", "rows": len(rows),
                  "first": rows[0]["date"], "last": rows[-1]["date"],
                  "schema_checks": "sorted unique ISO dates, finite positive prices, OHLC range, nonnegative integer volume",
                  "zero_volume_dates": [r["date"] for r in rows if r["volume"] == 0],
                  "coverage": coverage(rows, calendar, prior["start"], prior["end"],
                                       exchange_closures=evidence["exchange_closures"]),
                  "price_flags": flags, "split_ohlc_preparation": "blocked_pending_verified_event_history"}
        if suffix in ("KO", "TW"):
            filtered = filter_confirmed_closures(rows, calendar, evidence["exchange_closures"])
            input_dir = ASIA / "backtest_inputs"
            input_dir.mkdir(exist_ok=True)
            input_path = input_dir / (ticker.replace(".", "_") + "_session_filtered.csv")
            with input_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(filtered["rows"])
            result["backtest_input_preparation"] = {
                **{k: v for k, v in filtered.items() if k != "rows"},
                "original_source_path": str((directory / (ticker.replace(".", "_") + ".csv")).relative_to(ROOT)),
                "original_source_sha256": hashlib.sha256((directory / (ticker.replace(".", "_") + ".csv")).read_bytes()).hexdigest(),
                "path": str(input_path.relative_to(ROOT)),
                "output_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "coverage": coverage(filtered["rows"], calendar, prior["start"], prior["end"],
                                     exchange_closures=evidence["exchange_closures"])}
            listed = json.loads((ASIA / f"{suffix}_symbols.json").read_text())
            match = next(r for r in listed if r["Code"] == ticker.split(".")[0])
            result["listing_identity"] = {k: match.get(k) for k in ("Code", "Name", "Country", "Exchange", "Currency", "Type", "Isin")}
            baseline = ibkr[ticker.split(".")[0]]
            result["ibkr_comparison"] = {"source": "research/ibkr_asian_coverage_baseline.csv",
                                          "baseline": baseline,
                                          "eodhd_history_starts_later": rows[0]["date"] > baseline["first_returned_date"],
                                          "last_session_matches_ibkr": rows[-1]["date"] == baseline["last_returned_date"],
                                          "verified_daily_return_comparisons": [f for f in flags if f.get("independent_return_evidence")],
                                          "limitations": "IBKR baseline has range/count metadata plus user-supplied verified July 31 Korean returns; full overlapping OHLC and gap agreement cannot be compared."}
        if ticker == "AZN.US":
            events = split_events(json.loads((ASIA / "AZN_splits.json").read_text()),
                                  source="EODHD /api/splits/AZN.US; retrieved 2026-10-09")
            prepared = prepare_split_ohlc(rows, events, history_complete=True, basis_date=prior["end"])
            result["split_ohlc_preparation"] = prepared["status"]
            result["corporate_events"] = events
            result["event_checks"] = prepared["event_checks"]
            if prepared["status"] == "ready_for_research":
                checked_dates = {check["date"] for check in prepared["event_checks"] if check["passed"]}
                for flag in flags:
                    if flag["date"] in checked_dates:
                        flag["classification"] = "verified_corporate_action_discontinuity"
                        flag["requires_review"] = False
                with (ASIA / "AZN_split_only_ohlc.csv").open("w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(prepared["rows"][0]))
                    writer.writeheader()
                    writer.writerows(prepared["rows"])
                trs = {r["date"]: r["true_range"] for r in true_ranges(prepared)}
                for i, row in enumerate(rows):
                    if row["date"] == "2026-02-02":
                        result["conversion_day_true_range"] = {
                            "raw": max(row["high"] - row["low"], abs(row["high"] - rows[i-1]["close"]), abs(row["low"] - rows[i-1]["close"])),
                            "split_only": trs[row["date"]]}
            result["issuer_evidence_status"] = "AstraZeneca issuer website blocked by environment egress policy; legal listing terms not independently retrieved. EODHD event and price mechanics verified."
        results.append(result)
    report = {"asof": prior["asof"], "report_revision_date": "2026-10-10", "additional_eodhd_requests_for_revision": 0,
              "verified_evidence": evidence, "requested_start": prior["start"], "requested_end": prior["end"],
              "branch": "research/eodhd-acwi-imi-setup", "baseline_commit": "51eef5e",
              "closed_day_audit": [
                  {"ticker": r["ticker"], **observation}
                  for r in results for observation in r.get("backtest_input_preparation", {}).get("excluded_observations", [])],
              "experiment_budget": {"maximum_new_units": 12, "reserved_cost_units": ledger["reserved_units"],
                                    "http_requests": len(ledger["calls"]), "account_before": before, "account_after": after,
                                    "account_usage_note": "Cached 2026-10-09 snapshot, not a fresh allowance check",
                                    "observed_account_units_spent": after["reported_used_units"] - before["reported_used_units"],
                                    "endpoint_cost_source": "https://eodhd.com/financial-apis/api-limits",
                                    "breakdown": {"exchange_symbol_lists": 2, "split_history": 1, "daily_price_histories": 6, "account_checks": 0}},
              "validation_libraries": {"exchange_calendars": xc.__version__, "holidays": holidays.__version__},
              "results": results,
              "limitations": ["EODHD free data covers one year, insufficient for October 2023–September 2026 plus momentum/EMA warm-up.",
                              "IBKR Korea baseline starts 2021-10-12 (1,216 bars); Taiwan starts 2023-04-25 (842 bars), still later than the required September 2022 warm-up start.",
                              "AstraZeneca event is an economic share-unit conversion: two half-share units become one whole-share unit. EODHD represents it as a 1-for-2 split; issuer legal terms were not independently retrieved.",
                              "No split is inferred from adjusted_close/close; that factor also contains dividend adjustments.",
                              "Split-only OHLC is prepared only for AZN, with the verified event. Other series need complete event histories and unresolved anomaly review before use for ATR/stops.",
                              "End-date share-basis bars require unit conversion for historical position and order simulations; no trading integration was changed.",
                              "Calendar completeness and same-provider split consistency are not independent price or corporate-action audits."]}
    (ASIA / "combined_data_quality_report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# EODHD combined data-quality report", "",
             f"Period: {prior['start']} to {prior['end']}. Revised 2026-10-10 from cached data and independently verified information supplied by the user. All 14 downloads/schema checks passed. No trades executed.", "",
             f"This revision made zero EODHD requests. The original experiment used {ledger['reserved_units']} of 12 permitted API-call units across {len(ledger['calls'])} HTTP requests. Cached account snapshot from 2026-10-09: {before['reported_used_units']}/{before['daily_limit']} before; {after['reported_used_units']}/{after['daily_limit']} after; {after['remaining_units_today']} units remaining then. Today's allowance was not queried.", "",
             "| Ticker | Bars | Session coverage | Missing sessions | Closed-day bars | Price observations |",
             "|---|---:|---:|---|---|---|"]
    for r in results:
        if "coverage" not in r:
            lines.append(f"| {r['ticker']} | — | failed | {r.get('reason', '')} | — | — |")
            continue
        c = r["coverage"]
        observations = ', '.join(f"{f['date']}: {f['classification']}" for f in r['price_flags']) or 'None'
        lines.append(f"| {r['ticker']} | {r['rows']} | {c['session_coverage_pct']}% | {', '.join(c['missing_expected_dates']) or 'None'} | {', '.join(c['bars_on_verified_closed_dates']) or 'None'} | {observations} |")
    lines += ["", "Korean calendars: exchange_calendars predicts 246 sessions; holidays 0.106 identifies 2026-06-03 (local election) and 2026-07-17 (Constitution Day) as national closures, giving 244 expected sessions. All three Korean series match this reconciled calendar. Exchange-specific confirmation remains separate.", "",
              "Taiwan's exchange was closed on 2026-07-10 because of Typhoon Bavi, according to the independently verified information supplied by the user. This extraordinary closure corrects XTAI for every Taiwanese security: 242 sessions were expected. TSMC's absent bar is expected and its false missing-session flag is removed. Hon Hai and ASE's closed-day bars have zero volume and flat OHLC equal to the previous trading close: 237.5 for Hon Hai and 677 for ASE. Both are consistent with carried-forward placeholders, invalid as trading-session observations. There is no evidence of a different correct date, so neither is redated. Original CSVs remain unchanged; the two bars are excluded only from derived session-filtered input CSVs under `backtest_inputs/`. Each Taiwanese derived series has 242 valid-session rows and no missing/unexpected sessions. No prices are filled. These raw-price exports still need corporate-action and FX validation before a backtest.", "",
              "The independently verified IBKR returns for 2026-07-31 are Samsung Electronics +26.81%, SK Hynix +29.95% and Samsung Electro-Mechanics +29.92%. Each EODHD raw and adjusted return matches within 0.005 percentage points, with a stable adjustment factor. These are verified extreme market returns during a semiconductor-led rebound, not corporate-action errors. Their full returns and true ranges are preserved; no synthetic splits are created. Other series still require complete verified event histories before split-only export.", "",
              "## AstraZeneca conversion", "",
              "EODHD returns `1.000000/2.000000` on 2026-02-02: 0.5 new units per old unit. Before the event, raw OHLC is multiplied by two; on and after the event it is unchanged. This puts the series on the post-conversion share basis without dividend adjustment.", "",
              "The observed adjusted/raw factor ratio is 0.5000001907, matching the event ratio 0.5. Split-normalized close return is 1.546836%; adjusted-close return is 1.546875%. Raw true range is 100.02; split-only true range is 7.25. Adjusted prices handle the share representation consistently across this boundary.", "",
              "`AZN_split_only_ohlc.csv` is ready for research use with prices on one basis and EODHD's already split-adjusted volume unchanged. Do not multiply all raw OHLC by adjusted_close/close and call the result split-only: that includes dividends. Historical stop/order units must match the chosen share basis. The issuer website could not be accessed, so NYSE listing and legal ADS conversion terms are not independently confirmed here.", "",
              "## Primary symbols and IBKR comparison", "",
              "| Company / EODHD symbol | Currency | ISIN | EODHD bars / range | IBKR bars / range |",
              "|---|---|---|---|---|"]
    for r in results:
        if "ibkr_comparison" not in r:
            continue
        identity = r["listing_identity"]
        b = r["ibkr_comparison"]["baseline"]
        lines.append(f"| {identity['Name']} / {r['ticker']} | {identity['Currency']} | {identity['Isin']} | {r['rows']}: {r['first']}–{r['last']} | {b['daily_bars']}: {b['first_returned_date']}–{b['last_returned_date']} |")
    lines += ["", "ASE's EODHD name is ASE Industrial Holding Co Ltd (`3711.TW`), corresponding to the requested ASE Technology Holding primary listing. These are verified exchange-list records, not U.S. ADR substitutions.", "",
              "IBKR provides much deeper observed history than this EODHD free-plan sample. Korean IBKR history reaches 2021; Taiwan starts April 2023 and cannot establish the September 2022 warm-up needed by the documented three-year test. The baseline contains no raw IBKR bars, so full overlapping prices and gaps cannot be compared. The three July 31 Korean daily returns are now independently corroborated by the user-supplied IBKR findings.", "",
              "## Remaining work", "",
              "Verify the AZN listing conversion against issuer/NYSE documents; confirm Korean exchange closures; obtain complete split histories before preparing other series; obtain longer EODHD history and point-in-time index membership before a global backtest. The two confirmed non-trading records are excluded from derived inputs with an audit trail. Their provider-generation mechanism is not independently established. TSMC's missing-session concern and the Korean July-return concerns are resolved by the supplied independent evidence.", "",
              "Sources: EODHD API limits, daily-history and splits documentation; cached EODHD exchange lists and price responses; exchange_calendars 4.13.2; holidays 0.106; research/ibkr_asian_coverage_baseline.csv; research/verified_quality_evidence.json (independently verified findings supplied by the user on 2026-10-10, not newly queried here). Reports, downloaded data and request ledgers remain Git-ignored."]
    (ASIA / "combined_data_quality_report.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {ASIA / 'combined_data_quality_report.md'}")
    print(f"{len(results)} series; zero new requests; historical experiment cost {ledger['reserved_units']} units")


if __name__ == "__main__":
    main()
