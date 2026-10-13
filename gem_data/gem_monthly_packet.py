"""End-to-end GEMv1 monthly *manual* decision packet, without a broker.

Every run reports exactly which source gates block a safe ticket. It does
not elevate historical or alternative-provider data to certification.
"""
from __future__ import annotations

from hashlib import sha256
import json

from gem_data.gem_source_feature_verifier import recompute_full_month, SourceFeatureHold
from gem_data.gem_manual_ops import manual_trade_sheet, replay_manual_events, ManualLedgerHold
from gem_data.market_data_patch import reconcile_prices, PricePatchHold
from gem_data.historical_evidence_audit import audit_historical_claims


def _hash(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def build_monthly_packet(bundle: dict) -> dict:
    """Combine source QA, vendor-gap inventories, user ledger and manual tickets.

    Input shape:
      {schema, source_month, initial_cash, manual_events,
       reference_prices, price_gap_reviews?, history_claims?, history_evidence?,
       broker_statement?}

    A complete bundle is required for a trade sheet, but audit information
    remains available even when the signal is on HOLD. No side effects.
    """
    if not isinstance(bundle, dict) or bundle.get("schema") != "gem-manual-month-packet-v1":
        raise ValueError("Invalid manual month packet")
    gaps = []
    for review in bundle.get("price_gap_reviews", []):
        if not isinstance(review, dict):
            raise ValueError("Malformed price review")
        gaps.append(reconcile_prices(review["ticker"], review["sessions"], review["sources"]))
    history = audit_historical_claims(bundle.get("history_claims", []),
                                      bundle.get("history_evidence", []))
    ledger = replay_manual_events(bundle["initial_cash"], bundle.get("manual_events", []),
                                  bundle.get("broker_statement"))
    signal = None
    blockers = []
    try:
        signal = recompute_full_month(bundle["source_month"])
    except (SourceFeatureHold, ValueError, TypeError, KeyError) as exc:
        blockers.append({"scope": "SOURCE_MONTH", "reason": str(exc)[:220]})
    if signal is not None:
        if signal["data_status"] != "REVIEWED_COMPLETE":
            blockers.append({"scope": "RANKING_SOURCE_QA",
                             "reason": "One or more missing/uncertified monthly competitors"})
        if len(signal["selected"]) != 5:
            blockers.append({"scope": "FIVE_STOCK_RULE",
                             "reason": "Exactly five reviewed eligible stocks required"})
    if ledger["statement_status"] in ("STATEMENT_MISMATCH_HOLD", "STALE_MANUAL_STATEMENT"):
        blockers.append({"scope": "MANUAL_LEDGER",
                         "reason": "Imported brokerage statement differs from user-entered ledger"})
    if any(r["conflicts"] or r["unresolved_sessions"] or
           r["missing_original"] != r["corroborated_patch_candidates"] for r in gaps):
        blockers.append({"scope": "VENDOR_PRICE_GAPS",
                         "reason": "Some alternative price observations remain uncorroborated"})
    # Crosschecked nominal OHLCV does not imply split-adjusted momentum parity.
    if any(r["corroborated_patch_candidates"] for r in gaps):
        blockers.append({"scope": "ADJUSTED_PRICE_SEMANTICS",
                         "reason": "Corroborated nominal bars need adjustment review before ranking"})
    ticket = None
    if not blockers:
        try:
            ticket = manual_trade_sheet(signal, ledger, bundle["reference_prices"])
            if ticket["status"] != "INDICATIVE_USER_REVIEW_REQUIRED":
                blockers.append({"scope": "TRADE_SHEET", "reason": "Ticket generation held"})
                ticket = None
        except (ManualLedgerHold, ValueError, KeyError, TypeError) as exc:
            blockers.append({"scope": "TRADE_SHEET", "reason": str(exc)[:220]})
    result = {
        "schema": "gem-manual-month-result-v1",
        "mode": "MANUAL_BROKER_ONLY",
        "signal_session": bundle.get("source_month", {}).get("signal_session"),
        "status": "INDICATIVE_SHEET_READY_FOR_USER_REVIEW" if ticket else "DATA_HOLD",
        "blockers": blockers,
        "ranking": signal,
        "ledger": ledger,
        "vendor_gap_reports": gaps,
        "historical_review": history,
        "manual_trade_sheet": ticket,
        "broker_api_connected": False,
        "orders_submitted": 0,
        "automatic_execution": False,
        "historical_certification_granted": False,
    }
    result["packet_sha256"] = _hash(result)
    return result
