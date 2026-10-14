"""Evidence-driven integrity stages must show completed work without trading approval."""
from gem_data.gem_integrity_stages import describe_stages
from gem_data.gem_source_health import classify


def providers():
    return {
        "SECONDARY_GITHUB_SP500": {"receipt_count": 2},
        "WIKIPEDIA_SP500_CIK_CURRENT": {"receipt_count": 1},
        "SEC_ZIP_SUBMISSIONS": {"unique_members": 500},
        "SEC_ZIP_COMPANYFACTS": {"unique_members": 500},
        "NYSE_OFFICIAL": {"receipt_count": 1},
        "STATE_STREET_OFFICIAL_SPY_SCHEDULE": {"receipt_count": 1},
    }


def wiki_match():
    return {"security_lines": 503,
            "secondary_comparison": {
                "identity_match": True, "wikipedia_count": 503,
                "secondary_count": 503, "cik_mismatches": [],
                "only_wikipedia": [], "only_secondary": []}}


def describe(key, **changes):
    options = dict(providers=providers(), membership_count=503,
                   wiki_metrics=wiki_match(),
                   sec_pairs=500, sec_assessed=500, sec_candidate_complete=315,
                   marketstack_observed=6, verified_tickers=0,
                   action_scan_count=300)
    options.update(changes)
    return describe_stages(key, **options)


def test_matching_current_membership_is_visible_not_pit_certification():
    s = describe("membership")
    assert [r["state"] for r in s["stages"]] == [
        "COMPLETE", "COMPLETE", "COMPLETE", "PENDING"]
    assert "503 securities" in s["progress_summary"]
    assert s["source_approval"] == "NOT_APPROVED"


def test_disagreement_cannot_claim_current_identity_match():
    data = wiki_match()
    data["secondary_comparison"]["cik_mismatches"] = ["AAPL"]
    s = describe("membership", wiki_metrics=data)
    assert s["stages"][2]["state"] == "PENDING"


def test_sec_machine_assessment_complete_even_with_185_unknown():
    s = describe("sec")
    assert [r["state"] for r in s["stages"]] == [
        "COMPLETE", "PARTIAL", "COMPLETE", "PENDING"]
    assert "315 candidate-complete" in s["progress_summary"]


def test_corporate_8k_scans_progress_but_cannot_certify_mergers():
    s = describe("actions")
    assert s["stages"][0]["state"] == "PARTIAL"
    assert s["stages"][2]["state"] == "PENDING"
    assert "300" in s["progress_summary"]


def test_calendar_and_spy_schedule_are_recognized():
    assert describe("calendar")["stages"][0]["state"] == "COMPLETE"
    assert describe("benchmark")["stages"][0]["state"] == "COMPLETE"
    assert describe("benchmark")["stages"][-1]["state"] == "PENDING"


def test_marketstack_collected_six_is_not_six_verified():
    s = describe("prices")
    assert s["stages"][0]["state"] == "PARTIAL"
    assert s["stages"][2]["state"] == "PENDING"
    assert "6 Marketstack" in s["progress_summary"]


def test_no_evidence_no_green_stages():
    options = dict(providers={}, membership_count=0, wiki_metrics={},
                   sec_pairs=0, sec_assessed=0, sec_candidate_complete=0,
                   marketstack_observed=0, verified_tickers=0,
                   action_scan_count=0)
    for key in ("membership", "prices", "sec", "actions", "calendar", "benchmark"):
        assert all(stage["state"] == "PENDING"
                   for stage in describe_stages(key, **options)["stages"])


def test_full_source_overview_retains_data_hold():
    docs = [
        {"source_type": "membership", "provider": "SECONDARY_GITHUB_SP500",
         "receipt_count": 2, "unique_members": 0, "refreshed_at": None},
        {"source_type": "membership", "provider": "WIKIPEDIA_SP500_CIK_CURRENT",
         "receipt_count": 2, "unique_members": 0, "refreshed_at": None},
        {"source_type": "sec", "provider": "SEC_ZIP_SUBMISSIONS",
         "receipt_count": 1000, "unique_members": 500, "refreshed_at": None},
        {"source_type": "sec", "provider": "SEC_ZIP_COMPANYFACTS",
         "receipt_count": 1000, "unique_members": 500, "refreshed_at": None},
    ]
    result = classify(docs, [], {"inspected": 500,
                      "machine_complete": 315, "certified": 0},
                      membership_count=503,wiki_metrics=wiki_match(),
                      observed_marketstack=6,action_scan_count=300)
    membership=next(v for v in result["sources"] if v["key"]=="membership")
    assert membership["stages"][2]["state"]=="COMPLETE"
    assert result["investment_release"]=="DATA_HOLD"
    assert result["approved_monthly_signals"]==0
