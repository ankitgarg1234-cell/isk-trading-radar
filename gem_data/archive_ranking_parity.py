"""Offline GEMv1 per-month/per-stock archived-feature parity audit.

Independent recomputation of frozen gates from archived *features*, not SEC
certification. No network, database, broker, production import or mutation.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ("date", "ticker", "r63", "revenue_yoy", "earnings_improvement",
          "margin_delta_pp", "G", "E")


def numeric(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def truth(value):
    return str(value).strip().lower() in ("true", "1", "t")


def read_rows(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing archived feature columns: " + ", ".join(sorted(missing)))
        yield from reader


def audit(rows):
    groups = defaultdict(list)
    for row in rows:
        ds, ticker = row["date"], row["ticker"]
        if not ds or not ticker:
            raise ValueError("Missing date/ticker")
        groups[ds].append(row)
    detail, monthly = [], []
    for ds, group in sorted(groups.items()):
        if len({r["ticker"] for r in group}) != len(group):
            raise ValueError("Duplicate ticker on " + ds)
        inspected = []
        for row in group:
            momentum = numeric(row["r63"])
            growth = numeric(row["revenue_yoy"])
            margin = numeric(row["margin_delta_pp"])
            earnings = truth(row["earnings_improvement"])
            archived_growth = truth(row["G"])
            archived_earnings = truth(row["E"])
            archived_eligible = archived_growth and archived_earnings and margin is not None and margin > 3
            unknown = any(x is None for x in (momentum, growth, margin))
            recomputed = (growth is not None and growth > .2 and earnings
                          and margin is not None and margin > 3
                          and momentum is not None and momentum > 0)
            # Archived simulator selects by G/E/margin, not an explicit r63>0.
            # Record this as a genuine rule difference, never conceal it.
            archived_gate = archived_eligible
            reason = ("INSUFFICIENT_ARCHIVED_FEATURE_EVIDENCE" if unknown else
                      "FROZEN_GATE_DIFFERENCE" if archived_gate != recomputed else
                      "MATCH_ARCHIVED_FEATURES")
            inspected.append(dict(date=ds, ticker=row["ticker"], r63=momentum,
                                  revenue_yoy=growth, margin_delta_pp=margin,
                                  archived_G=archived_growth, archived_E=archived_earnings,
                                  archived_eligible=archived_gate,
                                  recomputed_eligible=recomputed, reason=reason))
        # pandas sort_values(score, ascending=False) defaults to quicksort.
        # Tie ordering cannot be independently certified from this CSV alone.
        archive = sorted((r for r in inspected if r["archived_eligible"]),
                         key=lambda r: -(r["r63"] if r["r63"] is not None else float("-inf")))
        fresh = sorted((r for r in inspected if r["recomputed_eligible"]),
                       key=lambda r: (-r["r63"], r["ticker"]))
        oldrank = {r["ticker"]: i + 1 for i, r in enumerate(archive)}
        newrank = {r["ticker"]: i + 1 for i, r in enumerate(fresh)}
        for r in inspected:
            r["archived_feature_rank"] = oldrank.get(r["ticker"])
            r["recomputed_rank"] = newrank.get(r["ticker"])
            r["rank_difference"] = (newrank[r["ticker"]] - oldrank[r["ticker"]]
                                    if r["ticker"] in oldrank and r["ticker"] in newrank else None)
            detail.append(r)
        monthly.append(dict(date=ds, inspected=len(group),
                            missing_feature_evidence=sum(r["reason"] == "INSUFFICIENT_ARCHIVED_FEATURE_EVIDENCE" for r in inspected),
                            gate_differences=sum(r["reason"] == "FROZEN_GATE_DIFFERENCE" for r in inspected),
                            archived_feature_top5="|".join(r["ticker"] for r in archive[:5]),
                            recomputed_top5="|".join(r["ticker"] for r in fresh[:5]),
                            top5_matches=[r["ticker"] for r in archive[:5]] ==
                                         [r["ticker"] for r in fresh[:5]]))
    return detail, monthly


def write_csv(path, rows):
    if not rows:
        raise ValueError("No monthly signals in input")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=HERE / "archived_signal_features.csv.gz")
    parser.add_argument("--out", type=Path, default=HERE / "parity")
    args = parser.parse_args()
    detail, monthly = audit(read_rows(args.features))
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "per_stock_month.csv", detail)
    write_csv(args.out / "monthly_rankings.csv", monthly)
    summary = dict(classification="ARCHIVED_FEATURE_REPLAY_NOT_INDEPENDENT_PIT_CERTIFICATION",
                   months=len(monthly), stock_month_rows=len(detail),
                   gate_differences=sum(m["gate_differences"] for m in monthly),
                   missing_feature_evidence=sum(m["missing_feature_evidence"] for m in monthly),
                   differing_top5_months=sum(not m["top5_matches"] for m in monthly),
                   blockers=["Archived panel excludes some unpriced S&P competitors",
                             "G/E/margin panel flags are not independently verified SEC inputs",
                             "Historical simulator does not explicitly require positive r63",
                             "Tie ordering differs between pandas default sort and ticker tie-break",
                             "Source certifications and execution parity are outside this audit"])
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
