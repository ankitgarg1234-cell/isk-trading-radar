"""GEM SEC nightly bulk ZIP strict safety + original receipt integration (no network)."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import zipfile
import httpx
import pytest

from gem_data.sec_bulk_zip_ingest import (
    ARCHIVES, BulkSourceHold, SECByteRangeFile, capture_bulk_batch,
    parse_selected_member,
)
from gem_data.gem_public_ingest import SECONDARY


def zip_bytes(name, cik, *, kind="submissions"):
    data = {"cik": int(cik)}
    if kind == "submissions":
        data["filings"] = {"recent": {
            "form": ["10-Q"], "accessionNumber": ["0001000000-26-000001"],
            "filingDate": ["2026-08-01"], "acceptanceDateTime": ["2026-08-01T10:00:00"],
        }}
    else:
        data["facts"] = {"us-gaap": {
            "OperatingIncomeLoss": {"units": {"USD": []}},
            "NetIncomeLoss": {"units": {"USD": []}},
            "Revenues": {"units": {"USD": []}},
        }}
    original = json.dumps(data).encode()
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, original)
    return buf.getvalue(), original


def client_with_ranges(archives, *, refuse_ranges=False, corrupt_range=False):
    csv = ("Symbol,CIK\n" + "".join(
        f"TEST{i},{1000000+i}\n" for i in range(500))).encode()
    def handler(req):
        uri = str(req.url)
        if uri == SECONDARY:
            return httpx.Response(200, content=csv)
        body = archives[uri]
        if req.method == "HEAD":
            return httpx.Response(200, headers={
                "content-length": str(len(body)),
                "last-modified": "Mon, 12 Oct 2026 09:00:00 GMT",
                "etag": '"stable-capture"',
            })
        rng = req.headers.get("range")
        if refuse_ranges:
            return httpx.Response(200, content=b"NO DOWNLOAD OF ENTIRE ARCHIVE")
        assert rng and rng.startswith("bytes=")
        low, high = map(int, rng.removeprefix("bytes=").split("-"))
        part = body[low:high+1]
        return httpx.Response(206, content=part, headers={
            "content-range": f"bytes {low}-{high}/{len(body) if not corrupt_range else 9999}",
        })
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_reads_valid_member_using_only_range_requests():
    cik = "0001000000"
    rawzip, original = zip_bytes(f"CIK{cik}.json", cik)
    with client_with_ranges({ARCHIVES["submissions"]: rawzip}) as c:
        stream = SECByteRangeFile(c, ARCHIVES["submissions"], min_delay=0)
        with zipfile.ZipFile(stream) as archive:
            with archive.open(f"CIK{cik}.json") as handle:
                raw = handle.read()
    assert raw == original
    assert stream.calls > 0
    assert parse_selected_member("submissions", cik, raw)["quarter_filing_refs"] == 1


def test_range_ignored_fails_closed_without_parsing_body():
    rawzip, _ = zip_bytes("CIK0001000000.json", "0001000000")
    with client_with_ranges({ARCHIVES["companyfacts"]: rawzip},
                            refuse_ranges=True) as c:
        stream = SECByteRangeFile(c, ARCHIVES["companyfacts"], min_delay=0)
        with pytest.raises(BulkSourceHold, match="ranges unavailable"):
            zipfile.ZipFile(stream)


def test_changed_range_rejected():
    rawzip, _ = zip_bytes("CIK0001000000.json", "0001000000")
    with client_with_ranges({ARCHIVES["submissions"]: rawzip},
                            corrupt_range=True) as c:
        stream = SECByteRangeFile(c, ARCHIVES["submissions"], min_delay=0)
        with pytest.raises(BulkSourceHold, match="range changed"):
            zipfile.ZipFile(stream)


def test_companyfacts_candidate_detection_not_certification():
    cik = "0001000000"
    _, original = zip_bytes("CIK0001000000.json", cik, kind="companyfacts")
    metrics = parse_selected_member("companyfacts", cik, original)
    assert metrics["available_us_gaap_fact_concepts"]["revenue"] == ["Revenues"]
    assert metrics["six_financial_fact_values_certified"] is False


def test_wrong_cik_fails_closed():
    with pytest.raises(BulkSourceHold, match="CIK identity mismatch"):
        parse_selected_member("companyfacts", "0001000000",
                              json.dumps({"cik": 9999, "facts": {}}).encode())


def test_all_selected_zip_members_stored_as_partial_originals(monkeypatch):
    cik = "0001000000"
    mockzips = {}
    for kind, uri in ARCHIVES.items():
        z, _ = zip_bytes(f"CIK{cik}.json", cik, kind=kind)
        mockzips[uri] = z
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,query,args=None): statements.append((query,args))
        def fetchall(self): return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def cursor(self): return Cursor()
        def commit(self): pass
    monkeypatch.setattr("gem_data.sec_bulk_zip_ingest.psycopg.connect",
                        lambda *args, **kwargs: Connection())
    monkeypatch.setenv("GEM_INGEST_DATABASE_URL",
                       "postgresql://gem_source_ingest_limited:private@localhost/gem_forward")
    monkeypatch.setenv("SEC_USER_AGENT","GEM Research approved@example.com")
    with client_with_ranges(mockzips) as client:
        data = capture_bulk_batch(client=client, max_ciks=1)
    assert data["new_members"] == 2
    assert data["attempted_ciks"] == 2
    inserts = [(q,p) for q,p in statements if "INSERT INTO gem_source_receipt" in q]
    assert len(inserts) == 2
    assert all(p[6] == "UNKNOWN" for _,p in inserts)
    assert all("source_raw_zlib_base64" in p[8] for _,p in inserts)
    assert all(json.loads(p[8])["original_six_fact_values_certified"] is False for _,p in inserts)
    probes = [(q,p) for q,p in statements if "INSERT INTO gem_source_probe" in q]
    assert all(p[3] == "PARTIAL" for _,p in probes)


def test_invalid_batch_rejected_before_any_http():
    with pytest.raises(BulkSourceHold, match="batch outside"):
        capture_bulk_batch(max_ciks=1000)


def test_streams_large_central_directory_without_loading_index():
    from gem_data.sec_zip_index import SelectedRemoteZip
    target = "CIK0001000000.json"
    _, original = zip_bytes(target, "0001000000")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for i in range(40000):
            z.writestr("dummy-" + str(i).zfill(8) + ("x"*85) + ".txt", "")
        z.writestr(target, original)
    archive_bytes = buf.getvalue()
    assert len(archive_bytes) > 4_000_000
    with client_with_ranges({ARCHIVES["submissions"]: archive_bytes}) as client:
        stream = SECByteRangeFile(client, ARCHIVES["submissions"], min_delay=0)
        index = SelectedRemoteZip(stream, {target})
        assert index.read_member(target) == original
        assert list(index.members) == [target]


def test_nightly_delta_skips_unchanged_original_bytes(monkeypatch):
    """New archive ETag, identical CRC/size => no raw re-download or duplicate receipt."""
    cik = "0001000000"
    mockzips = {
        uri: zip_bytes(f"CIK{cik}.json", cik, kind=kind)[0]
        for kind, uri in ARCHIVES.items()
    }
    saved = {"gem_source_receipt": set(), "gem_source_probe": set()}
    inserts = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, query, args=None):
            if "SELECT receipt_id" in query:
                prefix = args[0][:-1]
                self.rows = [(x,) for x in saved["gem_source_receipt"] if x.startswith(prefix)]
            elif "SELECT probe_id" in query:
                prefix = args[0][:-1]
                self.rows = [(x,) for x in saved["gem_source_probe"] if x.startswith(prefix)]
            elif "INSERT INTO gem_source_receipt" in query:
                saved["gem_source_receipt"].add(args[0])
                inserts.append(("receipt", args))
            elif "INSERT INTO gem_source_probe" in query:
                saved["gem_source_probe"].add(args[0])
                inserts.append(("probe", args))
        def fetchall(self): return getattr(self, "rows", [])
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()
        def commit(self): pass
    monkeypatch.setattr("gem_data.sec_bulk_zip_ingest.psycopg.connect",
                        lambda *args, **kwargs: Conn())
    monkeypatch.setenv("GEM_INGEST_DATABASE_URL",
                       "postgresql://gem_source_ingest_limited:private@localhost/gem_forward")
    monkeypatch.setenv("SEC_USER_AGENT", "GEM Research approved@example.com")

    # Mock client permits nightly ETag changes; byte-range response must
    # never return 200 or stream the entire SEC ZIP.
    def client_for(etag, payloads):
        csv = ("Symbol,CIK\n" + "".join(
            f"TEST{i},{1000000+i}\n" for i in range(500))).encode()
        def handler(req):
            uri = str(req.url)
            if uri == SECONDARY:
                return httpx.Response(200, content=csv)
            data = payloads[uri]
            if req.method == "HEAD":
                return httpx.Response(200, headers={
                    "content-length": str(len(data)), "etag": f'"{etag}"',
                    "last-modified": "Tue, 13 Oct 2026 06:00:00 GMT"})
            assert req.headers["if-range"] == f'"{etag}"'
            low, high = map(int, req.headers["range"][6:].split("-"))
            return httpx.Response(206, content=data[low:high+1], headers={
                "content-range": f"bytes {low}-{high}/{len(data)}"})
        return httpx.Client(transport=httpx.MockTransport(handler))

    with client_for("night-1", mockzips) as c:
        first = capture_bulk_batch(client=c, max_ciks=1)
    assert first["new_members"] == 2
    assert len(saved["gem_source_receipt"]) == 2
    assert len([x for x in saved["gem_source_probe"] if "-fp-" in x]) == 2

    with client_for("night-2", mockzips) as c:
        second = capture_bulk_batch(client=c, max_ciks=1)
    assert second["new_members"] == 0
    assert len(saved["gem_source_receipt"]) == 2
    assert all(second["kind"][k]["unchanged_skipped"] == 1 for k in ARCHIVES)
    assert len([x for x in saved["gem_source_probe"] if "-delta-" in x]) == 2

    # A changed companyfacts original must be downloaded and stored.
    changed = dict(mockzips)
    original = json.dumps({"cik": int(cik), "facts": {"us-gaap": {
        "OperatingIncomeLoss": {"units": {"USD": [123]}},
        "NetIncomeLoss": {"units": {"USD": []}},
        "Revenues": {"units": {"USD": []}}}}}).encode()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"CIK{cik}.json", original)
    changed[ARCHIVES["companyfacts"]] = buffer.getvalue()
    with client_for("night-3", changed) as c:
        third = capture_bulk_batch(client=c, max_ciks=1)
    assert third["kind"]["submissions"]["unchanged_skipped"] == 1
    assert third["kind"]["companyfacts"]["new_members"] == 1
    assert len(saved["gem_source_receipt"]) == 3


def test_delta_fingerprint_is_metadata_not_crypto_proof():
    from gem_data.sec_zip_index import SelectedRemoteZip
    cik = "0001000000"
    uri = ARCHIVES["submissions"]
    z, _ = zip_bytes(f"CIK{cik}.json", cik)
    with client_with_ranges({uri: z}) as c:
        source = SECByteRangeFile(c, uri, min_delay=0)
        index = SelectedRemoteZip(source, {f"CIK{cik}.json"})
        fingerprint = index.member_fingerprint(f"CIK{cik}.json")
        assert len(fingerprint) == 24
        assert fingerprint != sha256(index.read_member(f"CIK{cik}.json")).hexdigest()[:24]
