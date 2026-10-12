"""Fail-closed point-in-time checks for a proposed primary GEMv1 membership manifest.

This validates internal timing and identity consistency only. An unauthenticated
manifest can NEVER establish official S&P DJI origin, full completeness or QA
approval; a separate verifier must check its source bytes and sign the result.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re


class MembershipHold(ValueError):
    pass


_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


def _time(raw: object, label: str) -> datetime:
    if not isinstance(raw, str):
        raise MembershipHold("Missing timestamp for " + label)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MembershipHold("Invalid timestamp for " + label) from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise MembershipHold("Timezone-less timestamp for " + label)
    return result.astimezone(timezone.utc)


def _day(raw: object, label: str) -> date:
    if not isinstance(raw, str):
        raise MembershipHold("Missing date for " + label)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise MembershipHold("Invalid date for " + label) from exc


def audit_membership_manifest(manifest: object, universe: list[dict],
                              signal_day: date) -> str:
    """Validate as-of membership timing and exact security identity.

    Return the canonical proposal digest; this is NOT a certification token.
    The declared source hash is untrusted until original bytes are checked by
    an independent review service.
    """
    if not isinstance(manifest, dict) or manifest.get("schema") != "gem-primary-membership-manifest-v1":
        raise MembershipHold("Missing primary membership manifest")
    if _day(manifest.get("signal_session"), "signal session") != signal_day:
        raise MembershipHold("Membership manifest signal-session mismatch")
    cutoff = _time(manifest.get("decision_cutoff_at"), "decision cutoff")
    if cutoff.date() < signal_day or cutoff.date() > signal_day.fromordinal(signal_day.toordinal() + 1):
        raise MembershipHold("Membership decision cutoff outside signal boundary")
    observed = _time(manifest.get("first_observed_at"), "source first observed")
    published = _time(manifest.get("source_published_at"), "source publication")
    if observed > cutoff or published > cutoff or published > observed:
        raise MembershipHold("Primary membership source was not available by cutoff")
    fingerprint = manifest.get("source_sha256")
    if not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint):
        raise MembershipHold("Missing original membership source fingerprint")
    if (not isinstance(manifest.get("source_bytes"), int)
            or isinstance(manifest.get("source_bytes"), bool)
            or manifest["source_bytes"] <= 0):
        raise MembershipHold("Missing original membership source byte count")
    if not isinstance(manifest.get("source_uri"), str) or not manifest["source_uri"].startswith("https://"):
        raise MembershipHold("Missing source location for membership receipt")
    members = manifest.get("members")
    if not isinstance(members, list) or len(members) != len(universe):
        raise MembershipHold("Primary membership manifest does not cover all proposed members")
    declared = {}
    for row in members:
        if not isinstance(row, dict):
            raise MembershipHold("Malformed primary membership member")
        ticker, ident = row.get("ticker"), row.get("security_id")
        if not isinstance(ticker, str) or not ticker or not isinstance(ident, str) or not ident:
            raise MembershipHold("Missing member share-class/security identifier")
        if ident in declared:
            raise MembershipHold("Duplicated primary membership security identifier")
        effective = _day(row.get("effective_from"), ident + " effective_from")
        expiry = row.get("effective_until")
        if expiry is not None and _day(expiry, ident + " effective_until") <= signal_day:
            raise MembershipHold("Removed member still present at signal date")
        if effective > signal_day:
            raise MembershipHold("Future-effective member present at signal date")
        announcement = _time(row.get("announcement_observed_at"), ident + " announcement")
        if announcement > cutoff:
            raise MembershipHold("Member announcement unavailable at signal cutoff")
        declared[ident] = ticker
    expected = {r["security_id"]: r["ticker"] for r in universe}
    if len(expected) != len(universe) or declared != expected:
        raise MembershipHold("Primary membership identifiers do not match ranked universe")
    return sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
