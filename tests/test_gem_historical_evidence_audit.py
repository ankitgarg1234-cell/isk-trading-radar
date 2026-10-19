from gem_data.historical_evidence_audit import audit_historical_claims


def test_missing_primary_evidence_is_pending():
    report=audit_historical_claims([{"claim_id":"membership:A:2025-01-01","kind":"MEMBERSHIP","ticker":"A"}],[])
    assert report["pending"]==1 and report["reconciled"]==0


def test_verified_primary_receipt_reconciles():
    claim={"claim_id":"split:A:2025-01-01","kind":"CORPORATE_ACTION","ticker":"A"}
    receipt={"claim_id":claim["claim_id"],"source_sha256":"a"*64,
             "source_class":"PRIMARY","raw_bytes_verified":True,
             "effective_date_verified":True,"human_reviewed":True,
             "agrees_with_archive":True}
    assert audit_historical_claims([claim],[receipt])["reconciled"]==1


def test_disagreement_never_silently_certified():
    claim={"claim_id":"split:A:2025-01-01","kind":"CORPORATE_ACTION","ticker":"A"}
    receipt={"claim_id":claim["claim_id"],"source_sha256":"a"*64,
             "source_class":"PRIMARY","raw_bytes_verified":True,
             "agrees_with_archive":False}
    assert audit_historical_claims([claim],[receipt])["conflicts"]==1
