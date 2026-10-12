"""Validate publication/observation evidence; never retrieve current data."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from .common import ControlError, digest, sha256, utc


@dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    kind: str  # sec_fact, price_bar, membership, corporate_action
    security_id: str  # stable, historically mapped security identity
    content_sha256: str
    source_url: str
    event_at: str  # period end/bar close/effective event; never a future input
    published_at: str
    retrieved_at: str
    verified: bool
    publication_verifier_id: str
    sec_form: str = ""
    accession: str = ""
    raw_submission_sha256: str = ""
    filed_date: str = ""


def validate_evidence(evidence, signal_at, data_deadline_at, *, retrospective=False):
    """Conservative UTC validation with separate GEM prior-day SEC cutoff.

    data_deadline_at must be the exact end of the New York calendar day
    before the signal. A separate exchange calendar must certify signal time.
    Forward mode also requires acquisition before the signal. Historical repair
    permits later retrieval while insisting original publication was timely.
    """
    signal, deadline = utc(signal_at), utc(data_deadline_at)
    exchange_zone = ZoneInfo("America/New_York")
    signal_date = signal.astimezone(exchange_zone).date()
    cutoff_date = signal_date - timedelta(days=1)
    expected_deadline = (datetime.combine(signal_date, time.min, exchange_zone)
                         .astimezone(timezone.utc) - timedelta(microseconds=1))
    if deadline != expected_deadline:
        raise ControlError("SEC deadline must equal end of the prior New York calendar day")
    if not evidence:
        raise ControlError("No provenance evidence")
    identifiers = set()
    for item in evidence:
        if not isinstance(item, SourceEvidence):
            raise ControlError("Unknown evidence schema")
        if not item.source_id or item.source_id in identifiers:
            raise ControlError("Missing/duplicate source identity")
        identifiers.add(item.source_id)
        if not item.security_id or item.verified is not True or not item.publication_verifier_id:
            raise ControlError("Unverified source or historical identity")
        sha256(item.content_sha256)
        event, published, retrieved = utc(item.event_at), utc(item.published_at), utc(item.retrieved_at)
        if published > retrieved:
            raise ControlError("Retrieval predates publication")
        if event > signal or published > signal:
            raise ControlError("Future observation/publication")
        if not retrospective and retrieved > signal:
            raise ControlError("Forward run acquired data after its signal")
        if item.kind not in {"sec_fact", "price_bar", "membership", "corporate_action"}:
            raise ControlError("Unknown provenance kind")
        if item.kind in {"sec_fact", "price_bar"} and event > published:
            raise ControlError("Reported period/bar close occurs after its publication")
        url = urlparse(item.source_url)
        if url.scheme != "https" or not url.hostname:
            raise ControlError("Missing HTTPS source URL")
        if item.kind == "sec_fact":
            if url.hostname not in {"www.sec.gov", "sec.gov", "data.sec.gov"}:
                raise ControlError("SEC fact must point to primary SEC source")
            if not isinstance(item.sec_form, str) or not item.sec_form.startswith("10-Q") or not item.accession:
                raise ControlError("Frozen GEM financial gate admits 10-Q records, including amendments")
            sha256(item.raw_submission_sha256)
            try:
                filed = date.fromisoformat(item.filed_date)
            except ValueError as exc:
                raise ControlError("Missing SEC filing date") from exc
            if filed > cutoff_date or published > deadline:
                raise ControlError("SEC input misses prior-day cutoff")
    return digest([asdict(item) for item in evidence])
