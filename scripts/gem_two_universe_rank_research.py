"""Two secondary-universe versus frozen archived GEM-feature coverage audit.

Research-only. This does NOT run GEMv1 orders or amend the archived strategy.
It does NOT equate an archived feature row to point-in-time SEC certification.
Observed-only rank order is NOT a valid all-member rank when inputs are missing.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The operational GEM dashboard branch does not carry the frozen research
# archive. CI checks out the exact research commit into a read-only sidecar.
FROZEN_ROOT = ROOT / ".gem_frozen_archive"
sys.path.insert(0, str(ROOT / "scripts"))
from gem_public_membership_research import (
    SOURCE_HISTORY, MAX_BYTES, fetch_public_source, parse_history,
    asof_members, normalize_alias,
)
from gem_membership_identity_audit import identity_screen, screen_reference_symbols

SECONDARY_MONTHLY_PREFIX = (
    "https://raw.githubusercontent.com/pierrebrunelle/"
    "sp500-historical-constituents/main/data/spy"
)
ARCHIVE = FROZEN_ROOT / "research_5x/gem_2025_2026_validation"
ARCHIVE_PRICE = FROZEN_ROOT / "backtests/staged/wf3_prices.json.gz"
FROZEN_ENGINE = FROZEN_ROOT / "research_5x/code/run_research.py"
FROZEN_ENGINE_SHA = "a46271c5436a9fdec93af55705623a270c2888b0124814cf90af873d54ecf7b5"
FROZEN_COMMIT = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"


def monthly_source_url(year: int, month: int) -> str | None:
    # The second public archive has no files past April 2026 as inspected in
    # its repository tree on 2026-10-12. Never synthesize newer references.
    if not (2022 <= year <= 2026 and 1 <= month <= 12):
        return None
    if (year, month) > (2026, 4):
        return None
    return SECONDARY_MONTHLY_PREFIX + f"{year}{month:02d}"


def parse_monthly(raw: bytes) -> tuple[set[str], dict[str, str]]:
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("Monthly source not UTF-8") from exc
    names: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 2 or not cols[0].strip():
            raise ValueError("Malformed reference monthly constituent")
        ticker = normalize_alias(cols[0])
        if ticker in names:
            raise ValueError("Duplicate secondary reference ticker")
        names[ticker] = cols[1].strip()
    if not 400 <= len(names) <= 600:
        raise ValueError("Implausible public monthly source size")
    return set(names), names


def research_calendar(start="2021-01-01", end="2026-09-30") -> tuple[list[date], dict[str, list[str]]]:
    import pandas_market_calendars as mcal
    sessions = mcal.get_calendar("NYSE").valid_days(start_date=start, end_date=end)
    all_sessions = [x.date() for x in sessions]
    bymonth: dict[str, list[str]] = defaultdict(list)
    for d in all_sessions:
        bymonth[d.strftime("%Y-%m")].append(d.isoformat())
    last = [date.fromisoformat(days[-1]) for days in bymonth.values()]
    return last, bymonth


def load_archived_features() -> tuple[dict[str, dict[str, dict]], dict[str, list[str]]]:
    if hashlib.sha256(FROZEN_ENGINE.read_bytes()).hexdigest() != FROZEN_ENGINE_SHA:
        raise ValueError("Frozen engine bytes drift; refuse approximate rank replay")
    archive = ARCHIVE / "archived_signal_features.csv.gz"
    panel: dict[str, dict[str, dict]] = defaultdict(dict)
    with gzip.open(archive, "rt", newline="") as fh:
        for row in csv.DictReader(fh):
            day = row.get("date")
            symbol = normalize_alias(row.get("ticker", ""))
            if day in panel and symbol in panel[day]:
                raise ValueError("Duplicate archived price/fundamental feature")
            if day and symbol:
                panel[day][symbol] = row
    if not panel:
        raise ValueError("Frozen archived features absent")

    baseline: dict[str, list[str]] = {}
    with (ARCHIVE / "signals.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("policy") != "original":
                continue
            if row.get("experiment") not in {"A_2025", "B_2026_YTD"}:
                continue
            d = row["date"]
            chosen = row["tickers"].split("|") if row["tickers"] else []
            if d in baseline and baseline[d] != chosen:
                raise ValueError("Conflicting frozen baseline selections")
            baseline[d] = chosen
    return panel, baseline


def conditional_top5(rows: dict[str, dict], symbols: set[str]) -> list[str]:
    """Exact growth_margin5 archived-factor cutoffs, observed rows only.

    Source engine already prefilters raw_close>=5, ADV20>=10m, r126
    warmup. Here we use only those originally archived feature rows,
    not price/SEC values from the future or a newly tuned strategy.
    """
    qualified = []
    for ticker, row in rows.items():
        if ticker not in symbols:
            continue
        try:
            momentum = float(row["r63"])
            revenue_growth = float(row["revenue_yoy"])
            margin = float(row["margin_delta_pp"])
        except (TypeError, ValueError, KeyError):
            continue
        earnings = str(row.get("earnings_improvement", "")).lower() in ("true", "1")
        if (math.isfinite(momentum) and math.isfinite(revenue_growth)
                and math.isfinite(margin) and momentum > 0
                and revenue_growth > .2 and earnings and margin > 3):
            qualified.append((ticker, momentum))
    return [ticker for ticker, _ in sorted(qualified, key=lambda x: (-x[1], x[0]))[:5]]


def classify_month(signal_date: date, a_symbols: set[str], b_symbols: set[str] | None,
                   panel: dict[str, dict[str, dict]], baseline: dict[str, list[str]],
                   price_coverage: dict[str, set[str]] | None = None) -> dict:
    day = signal_date.isoformat()
    rows = panel.get(day)
    a_observed = conditional_top5(rows, a_symbols) if rows else []
    b_observed = conditional_top5(rows, b_symbols) if (rows and b_symbols is not None) else []
    initial = baseline.get(day)
    all_rank = conditional_top5(rows, set(rows)) if rows else []
    baseline_matches = initial == all_rank if initial is not None else None
    input_a = set(rows or {}) & a_symbols
    input_b = set(rows or {}) & b_symbols if b_symbols is not None else set()
    # A missing archived feature can mean insufficient price/liquidity, a
    # missing record, or missing fundamentals. NEVER call it a failed gate.
    missing_a = a_symbols - input_a
    missing_b = b_symbols - input_b if b_symbols is not None else set()
    disputed = (a_symbols ^ b_symbols) if b_symbols is not None else set()
    disputed_observed = disputed & set(rows or {})
    disputed_qualified = conditional_top5(rows, disputed_observed) if rows else []
    result = {
        "signal_session": day,
        "source_A_member_count": len(a_symbols),
        "source_B_member_count": len(b_symbols) if b_symbols is not None else None,
        "members_only_A": sorted(a_symbols - b_symbols) if b_symbols is not None else [],
        "members_only_B": sorted(b_symbols - a_symbols) if b_symbols is not None else [],
        "member_symmetric_difference_count": len(a_symbols ^ b_symbols) if b_symbols is not None else None,
        "disputed_members_with_archived_feature": sorted(disputed_observed),
        "disputed_members_qualified_on_archived_features": disputed_qualified,
        "archived_original_selected_missing_from_A": sorted(set(initial or []) - a_symbols) if initial is not None else None,
        "archived_original_selected_missing_from_B": (sorted(set(initial or []) - b_symbols)
                                                    if initial is not None and b_symbols is not None else None),
        "archived_feature_rows": len(rows) if rows else 0,
        "source_A_observed_feature_rows": len(input_a),
        "source_B_observed_feature_rows": len(input_b) if b_symbols is not None else None,
        "source_A_missing_feature_count": len(missing_a),
        "source_B_missing_feature_count": len(missing_b) if b_symbols is not None else None,
        "source_A_missing_feature_symbols": sorted(missing_a),
        "source_B_missing_feature_symbols": sorted(missing_b) if b_symbols is not None else [],
        "archived_original_top5": initial,
        "archived_top5_reconstructed_from_features": all_rank if rows else None,
        "baseline_feature_reproduction_match": baseline_matches,
        "observed_only_top5_A": a_observed if rows else None,
        "observed_only_top5_B": b_observed if (rows and b_symbols is not None) else None,
        "observed_only_top5_differ": (a_observed != b_observed) if (rows and b_symbols is not None) else None,
        "ranking_validated": False,
        "paper_execution_authorized": False,
    }
    if b_symbols is None:
        result["comparison_status"] = "NO_SECOND_PUBLIC_MONTHLY_REFERENCE"
    elif rows is None:
        result["comparison_status"] = "NO_FROZEN_ARCHIVED_FEATURES_FOR_MONTH"
    elif baseline_matches is False:
        result["comparison_status"] = "FROZEN_ARCHIVE_REPRODUCTION_MISMATCH"
    else:
        result["comparison_status"] = "CONDITIONAL_ARCHIVED_FEATURE_RESEARCH_ONLY"
    if price_coverage is not None:
        price_a = a_symbols & price_coverage.get(day, set())
        result["source_A_127_complete_bar_names"] = len(price_a)
        result["source_A_127_complete_bar_missing_symbols"] = sorted(a_symbols-price_a)
        if b_symbols is not None:
            price_b = b_symbols & price_coverage.get(day, set())
            result["source_B_127_complete_bar_names"] = len(price_b)
            result["source_B_127_complete_bar_missing_symbols"] = sorted(b_symbols-price_b)
    return result


def archived_price_coverage(dates: list[date], bymonth: dict[str, list[str]]) -> dict[str, set[str]]:
    """Diagnose existing vendor bar coverage, not price correctness or QA."""
    with gzip.open(ARCHIVE_PRICE, "rt") as fh:
        raw = json.load(fh)
    price_dates = {}
    for ticker, obj in raw.get("market", {}).items():
        by = {}
        for row in obj.get("rows", []):
            day = row.get("date")
            if day and row.get("close") is not None and row.get("open") is not None and row.get("volume") is not None:
                by[day] = row
        price_dates[normalize_alias(ticker)] = set(by)
    all_sessions = [v for month in bymonth.values() for v in month]
    pos = {d: i for i, d in enumerate(all_sessions)}
    out = {}
    for signal in dates:
        day = signal.isoformat()
        if day not in pos or pos[day] < 126:
            out[day] = set()
            continue
        expected = set(all_sessions[pos[day]-126:pos[day]+1])
        out[day] = {ticker for ticker, available in price_dates.items() if expected.issubset(available)}
    return out


def research_run(out: Path, raw_dir: Path, include_prices: bool = True) -> dict:
    if out.exists() or raw_dir.exists():
        raise FileExistsError("Refusing overwrite of historical research evidence")
    raw_dir.mkdir(parents=True)
    history_raw = fetch_public_source(SOURCE_HISTORY)
    (raw_dir / "constituents-intervals.csv").write_bytes(history_raw)
    source_receipts = [{
        "url": SOURCE_HISTORY,
        "sha256": hashlib.sha256(history_raw).hexdigest(),
        "bytes": len(history_raw),
        "classification": "PUBLIC_SECONDARY_RESEARCH",
    }]
    history = parse_history(history_raw)
    panel, baseline = load_archived_features()
    months, bymonth = research_calendar()
    dates = [d for d in months if date(2022, 1, 1) <= d <= date(2026, 9, 30)]
    price_coverage = archived_price_coverage(dates, bymonth) if include_prices else None
    comparisons, errors = [], []
    for signal in dates:
        day = signal.isoformat()
        month = signal.strftime("%Y-%m")
        a = asof_members(history, signal)
        a_review = identity_screen(a, signal)
        a_set = set(a_review["retained"])
        uri = monthly_source_url(signal.year, signal.month)
        b_set = None
        b_review = None
        if uri:
            try:
                req = urllib.request.Request(uri, headers={"User-Agent": "GEM-monthly-research/1.0"})
                with urllib.request.urlopen(req, timeout=25) as response:
                    raw = response.read(MAX_BYTES+1)
                if not raw or len(raw) > MAX_BYTES:
                    raise ValueError("Missing/oversized historical monthly source")
                symbols, descriptions = parse_monthly(raw)
                b_review = screen_reference_symbols(symbols, signal, names=descriptions)
                b_set = set(b_review["retained"])
                (raw_dir / (signal.strftime("spy%Y%m")+".txt")).write_bytes(raw)
                source_receipts.append({
                    "url": uri, "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw), "signal_date": day,
                    "classification": "PUBLIC_SECONDARY_RESEARCH",
                })
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                errors.append({"month": month, "source": uri, "error_type": type(exc).__name__})
        result = classify_month(signal, a_set, b_set, panel, baseline, price_coverage)
        result["source_A_quarantined"] = a_review["quarantined"]
        result["source_A_unresolved_CIK_collisions"] = a_review["unresolved_same_cik_collisions"]
        result["source_A_after_cutoff_created_count"] = sum(x["first_source_recorded_on"] > signal for x in a)
        result["source_B_quarantined"] = b_review["quarantined"] if b_review else []
        result["source_B_uncertain_identity"] = b_review["uncertain_identity"] if b_review else []
        result["source_B_uri"] = uri
        result["archive_sec_original_all_competitors_certified"] = False
        result["primary_membership_certified"] = False
        result["top5_change_conclusion"] = "INDETERMINATE_INCOMPLETE_RANKING_EVIDENCE"
        comparisons.append(result)
    report = {
        "schema": "gem-v1-two-universe-ranking-research-v1",
        "frozen_strategy_commit": FROZEN_COMMIT,
        "frozen_engine_sha256": FROZEN_ENGINE_SHA,
        "classification": "RESEARCH_ONLY_NOT_PIT_CERTIFIED",
        "rank_authorized": False, "paper_execution_authorized": False,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_A": SOURCE_HISTORY,
        "source_B_prefix": SECONDARY_MONTHLY_PREFIX,
        "month_count": len(comparisons),
        "months_compared_with_both_memberships": sum(x["source_B_member_count"] is not None for x in comparisons),
        "months_with_archived_features": sum(x["archived_feature_rows"] > 0 for x in comparisons),
        "months_with_conditional_observed_rank_difference": sum(x["observed_only_top5_differ"] is True for x in comparisons),
        "months_with_full_verified_top5": 0,
        "source_receipts": source_receipts,
        "retrieval_errors": errors,
        "monthly": comparisons,
        "limitations": [
            "Both memberships are public retrospective sources, not official as-known constituents.",
            "Symbol-era quarantine is not issuer action settlement or original source verification.",
            "2022–2023 missing archived SEC/price feature tape is not filled with future facts.",
            "Archived panel prefilters liquidity/price/warmup; absence is UNKNOWN, not failure.",
            "Archive SEC competitors unresolved (943 prior gap triage); no complete source QA.",
            "2026 May–September second-source monthly files do not exist in repository.",
            "Conditional observed-only top-five must not be represented as actual GEM selections.",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--skip-price-coverage", action="store_true")
    args = parser.parse_args()
    report = research_run(Path(args.out), Path(args.raw_dir), not args.skip_price_coverage)
    concise = []
    for row in report["monthly"]:
        concise.append({
            "month": row["signal_session"], "A": row["source_A_member_count"],
            "B": row["source_B_member_count"],
            "diff": row["member_symmetric_difference_count"],
            "conditional_rank_different": row["observed_only_top5_differ"],
            "rank_reproduction_match": row["baseline_feature_reproduction_match"],
            "A_price_127_names": row.get("source_A_127_complete_bar_names"),
            "B_price_127_names": row.get("source_B_127_complete_bar_names"),
            "status": row["comparison_status"],
        })
    print(json.dumps({
        "classification": report["classification"],
        "months": report["month_count"],
        "two_source_months": report["months_compared_with_both_memberships"],
        "with_archived_features": report["months_with_archived_features"],
        "conditional_rank_differences": report["months_with_conditional_observed_rank_difference"],
        "top5_fully_verified": 0,
        "retrieval_errors": report["retrieval_errors"],
        "summary": concise,
    }, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
