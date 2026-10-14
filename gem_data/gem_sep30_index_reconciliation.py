"""Targeted Sept 30, 2026 PIT member corrections from original S&P notice.

Issuer primary source:
https://press.spglobal.com/2026-10-01-Vylor-Added-to-the-S-P-500-Twilio-Set-to-Join-S-P-500-Others-to-Join-S-P-MidCap-400-and-S-P-SmallCap-600

As-of 2026-09-30 CTVA and WBD were constituents. The October 13
secondary list instead includes VYLR and TWLO after index replacements.
Do NOT extrapolate this two-event repair into complete historical PIT coverage.
"""
from __future__ import annotations

from hashlib import sha256
import json

REPLACEMENTS = {
    "VYLR": {"ticker":"CTVA","cik":"0001755672",
             "effective_addition":"2026-10-01"},
    "TWLO": {"ticker":"WBD","cik":"0001437107",
             "effective_addition":"2026-10-06"},
}
NOTICE="https://press.spglobal.com/2026-10-01-Vylor-Added-to-the-S-P-500-Twilio-Set-to-Join-S-P-500-Others-to-Join-S-P-MidCap-400-and-S-P-SmallCap-600"


def adjust_sep30_current_membership(current):
    if not isinstance(current,dict) or len(current)!=503:
        raise ValueError("Expected 503 current security identities")
    if not all(isinstance(k,str) and isinstance(v,str) for k,v in current.items()):
        raise ValueError("Missing constituent ticker/CIK")
    members=current.copy()
    for after,before in REPLACEMENTS.items():
        if after not in members or before["ticker"] in members:
            raise ValueError("Known S&P Oct replacement not consistent with current source")
        members.pop(after)
        members[before["ticker"]]=before["cik"]
    if len(members)!=503 or len(set(members.values()))!=500:
        raise ValueError("September 30 issuer security count mismatched")
    evidence={"schema":"gem-sep30-known-pit-2026-corrections-v1",
              "signal_day":"2026-09-30",
              "official_source":NOTICE,
              "current_snapshot_count":len(current),
              "corrected_snapshot_count":len(members),
              "removed_post_signal":["VYLR","TWLO"],
              "restored_prior_members":["CTVA","WBD"],
              "members":dict(sorted(members.items())),
              "historical_membership_full_audit_complete":False,
              "independent_source_signoff":False,
              "ranking_authorized":False,"trading_authorized":False}
    evidence["sha256"]=sha256(json.dumps(
        evidence,sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode()).hexdigest()
    return evidence
