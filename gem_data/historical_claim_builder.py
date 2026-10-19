"""Extract frozen historical membership/corporate-action claims for primary QA.

Archives are read only. This builds an *audit worklist*, not invented
certification. Historical ticker membership is never substituted by today's
S&P 500 membership. Events are grouped by source date and impact on positions.
"""
from __future__ import annotations

import argparse
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path

from gem_data.historical_evidence_audit import audit_historical_claims


def _held_on(trades, ticker, day):
    per_experiment = {}
    for trade in sorted(trades, key=lambda row: row["date"]):
        if trade.get("ticker") != ticker or trade.get("policy") != "original" or trade["date"] > day:
            continue
        exp = trade.get("experiment")
        qty = float(trade["shares"])
        n = per_experiment.get(exp, 0.0)
        per_experiment[exp] = n + (qty if trade["side"] == "BUY" else -qty)
    return any(q > 0 for q in per_experiment.values())


def build_claims(archived, *, trades=(), signals=(), start="2025-01-01", end="2026-10-09"):
    market = archived.get("market")
    membership = archived.get("membership")
    if not isinstance(market, dict) or not isinstance(membership, dict):
        raise ValueError("Unrecognized frozen market input")
    selected = set()
    for row in signals:
        if row.get("policy") == "original" and start <= row.get("date", "") <= end:
            selected.update(x for x in row.get("tickers", "").split("|") if x)
    claims = []
    for change in membership.get("changes", []):
        day = change.get("date", "")
        if not start <= day <= end:
            continue
        for action, field in (("ADDITION", "added"), ("DELETION", "removed")):
            ticker = change.get(field)
            if not ticker:
                continue
            claims.append({
                "claim_id": f"sp500:{day}:{action}:{ticker}",
                "kind": "MEMBERSHIP", "ticker": ticker,
                "effective_date": day, "change": action,
                "impact": "SIGNAL_CANDIDATE_OR_MEMBER" if ticker in selected else "OTHER_CONSTITUENT",
                "archive_origin": "RECONSTRUCTED_SECONDARY_MEMBERSHIP",
                "required_proof": "S&P DJI primary dated announcement and effective date",
            })
    for ticker, obj in market.items():
        if not isinstance(obj, dict):
            continue
        def impact_on(day):
            return ("HELD_DURING_REPLAY" if _held_on(trades, ticker, day) else
                    "SIGNAL_SELECTED" if ticker in selected else "OTHER_CONSTITUENT")
        for entry in obj.get("splits", []):
            day = entry.get("date", "")
            if start <= day <= end:
                claims.append({
                    "claim_id": f"action:{day}:SPLIT:{ticker}",
                    "kind": "CORPORATE_ACTION", "ticker": ticker,
                    "effective_date": day, "change": "SPLIT",
                    "ratio": [entry.get("numerator"), entry.get("denominator")],
                    "impact": impact_on(day), "archive_origin": "FROZEN_VENDOR_SPLIT",
                    "required_proof": "Issuer split effective date and economic ratio",
                })
        for entry in obj.get("dividends", []):
            day = entry.get("date", "")
            if start <= day <= end:
                claims.append({
                    "claim_id": f"action:{day}:DIVIDEND:{ticker}",
                    "kind": "CORPORATE_ACTION", "ticker": ticker,
                    "effective_date": day, "change": "DIVIDEND",
                    "amount": entry.get("amount"), "impact": impact_on(day),
                    "archive_origin": "VENDOR_DISTRIBUTION_DATE_UNVERIFIED",
                    "required_proof": "Issuer ex-date, record-date, payable-date, cash per share",
                })
    # The archived engine also has special spinoff handling. These are
    # explicit worklist claims, NOT new adjustments inserted in old prices.
    for ticker, child, day in (("WDC", "SNDK", "2025-02-24"),
                               ("GE", "GEV", "2024-04-02"),
                               ("MMM", "SOLV", "2024-04-01")):
        if start <= day <= end:
            claims.append({
                "claim_id": f"action:{day}:SPINOFF:{ticker}:{child}",
                "kind": "CORPORATE_ACTION", "ticker": ticker,
                "effective_date": day, "change": "SPINOFF", "child_ticker": child,
                "impact": "HELD_DURING_REPLAY" if _held_on(trades, ticker, day) else
                          "SIGNAL_SELECTED" if ticker in selected else "OTHER_CONSTITUENT",
                "archive_origin": "RESEARCH_ENGINE_SPECIAL_SPINOFF",
                "required_proof": "Issuer distribution ratio, when-issued terms, payable date",
            })
    ids = [c["claim_id"] for c in claims]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicated event identity in archive input")
    priority = {"HELD_DURING_REPLAY": 0, "SIGNAL_SELECTED": 1,
                "SIGNAL_CANDIDATE_OR_MEMBER": 2, "OTHER_CONSTITUENT": 3}
    claims.sort(key=lambda x: (priority.get(x["impact"], 9), x["effective_date"], x["claim_id"]))
    return claims


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--prices-gz", type=Path, required=True)
    p.add_argument("--trades", type=Path, required=True)
    p.add_argument("--signals", type=Path, required=True)
    p.add_argument("--evidence", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args=p.parse_args()
    with gzip.open(args.prices_gz, "rt") as fh:
        archived=json.load(fh)
    with args.trades.open(newline="") as f:
        trades=list(csv.DictReader(f))
    with args.signals.open(newline="") as f:
        signals=list(csv.DictReader(f))
    claims=build_claims(archived, trades=trades, signals=signals)
    evidence=json.loads(args.evidence.read_text()) if args.evidence else []
    review=audit_historical_claims(claims, evidence)
    payload={"classification":"FROZEN_HISTORICAL_CLAIMS_NOT_FULLY_CERTIFIED",
             "claims": claims, "review": review,
             "original_market_archive_sha256":sha256(args.prices_gz.read_bytes()).hexdigest()}
    if args.out.exists():
        raise ValueError("Will not overwrite historical review output")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"claims":len(claims),"primary_reconciled":review["reconciled"],
                      "pending":review["pending"],"conflicts":review["conflicts"]}))


if __name__ == "__main__":
    main()
