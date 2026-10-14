"""Python machine QA flags can PASS narrow checks but never release trades."""
from datetime import datetime,timezone
import pytest
from gem_data.gem_python_machine_qa import (
    project_machine_qa,MachineEvidenceUnavailable,
)
from gem_data.gem_autonomous_release import evaluate_release
from tests.test_gem_autonomous_release import facts


def fixtures():
    i,p,l=facts()
    i["membership_security_lines"]=503
    i["corporate_issuer_scans"]=500
    i["sources"]=[
      {"key":key,"status":"PARTIAL","source_approval":"NOT_APPROVED",
       "progress_tag":"UNVERIFIED",
       "stages":[{"name":"published","state":"COMPLETE"},
                 {"state":"COMPLETE"},
                 {"state":"COMPLETE" if key=="membership" else "PENDING"}]}
      for key in ("membership","prices","sec","actions","calendar","benchmark")
    ]
    p["collection"].update({"histories_with_at_least_127_bars":491,
                            "histories_with_rejected_vendor_rows":481})
    p["stored_receipt_audit"].update({"audited":499,"integrity_pass":499})
    p["yahoo_research"]={"stored_personal_research_candidates":100,
                         "targeted_vendor_close_gaps":1321}
    sec={"paired_issuers":500,"original_sha_pass":500,
         "six_fact_candidate_complete":316,"missing_or_ambiguous":184}
    return i,p,l,sec


def test_existing_originals_pass_six_narrow_machine_properties():
    i,p,l,sec=fixtures()
    result=project_machine_qa(i,p,sec,
        at=datetime(2026,10,14,16,tzinfo=timezone.utc))
    assert result["schema"]=="gem-python-machine-qa-v1"
    assert result["machine_checks_total"]==10
    assert result["machine_checks_passed"]==6
    lookup={g["key"]:g for g in result["checks"]}
    assert lookup["original_sec_member_sha"]["passed"] is True
    assert lookup["marketstack_receipt_sha_ohlc"]["passed"] is True
    assert lookup["current_member_cik_crosscheck"]["passed"] is True
    assert lookup["published_nyse_schedule"]["passed"] is True
    assert lookup["published_spy_distribution_schedule"]["passed"] is True
    assert lookup["issuer_action_discovery"]["passed"] is True
    for key in ("complete_vendor_daily_histories",
                "sec_machine_six_fact_candidate",
                "yahoo_personal_gap_discovery","ibkr_yahoo_historical_ohlcv_agreement"):
        assert lookup[key]["passed"] is False
    assert result["independent_source_approval"] is False
    assert result["trading_enabled"] is False


def test_machine_passes_cannot_unlock_source_approval():
    i,p,l,sec=fixtures()
    passed=project_machine_qa(i,p,sec)
    release=evaluate_release(i,p,l,machine_qa=passed)
    assert release["production_trading_ready"] is False
    assert release["research_inputs_ready"] is False
    assert "source_sec" in release["blocked_gates"]
    assert release["python_machine_qa"]["machine_checks_passed"]==6


@pytest.mark.parametrize("alter",[
    lambda i,p,s: s.update(original_sha_pass=501),
    lambda i,p,s: s.update(six_fact_candidate_complete=501),
    lambda i,p,s: s.update(missing_or_ambiguous=500),
    lambda i,p,s: p["stored_receipt_audit"].update(integrity_pass=500),
    lambda i,p,s: p["collection"].update(security_lines_target=499),
    lambda i,p,s: i["sources"].pop(),
    lambda i,p,s: p["yahoo_research"].update(stored_personal_research_candidates=1322),
    lambda i,p,s: i.update(corporate_issuer_scans=None),
])
def test_broken_snapshot_does_not_pass(alter):
    i,p,l,s=fixtures()
    alter(i,p,s)
    with pytest.raises(MachineEvidenceUnavailable):
        project_machine_qa(i,p,s)


def test_sha_success_can_coexist_with_ambiguous_sec_facts():
    i,p,l,sec=fixtures()
    sec["six_fact_candidate_complete"]=0
    sec["missing_or_ambiguous"]=500
    result=project_machine_qa(i,p,sec)
    d={x["key"]:x for x in result["checks"]}
    assert d["original_sec_member_sha"]["passed"] is True
    assert d["sec_machine_six_fact_candidate"]["passed"] is False


def test_machine_input_cannot_self_certify_sources():
    i,p,l,sec=fixtures()
    result=project_machine_qa(i,p,sec)
    result["independent_source_approval"]=True
    with pytest.raises(Exception):
        evaluate_release(i,p,l,machine_qa=result)


def test_reject_naive_machine_clock():
    i,p,l,sec=fixtures()
    with pytest.raises(MachineEvidenceUnavailable):
        project_machine_qa(i,p,sec,at=datetime(2026,10,14,16))


def test_broker_independent_price_match_is_numeric_only():
    i,p,l,sec=fixtures()
    report=project_machine_qa(i,p,sec,ibkr_audit={"compared":100,"agreed":100,"conflicts":0})
    state={x["key"]:x for x in report["checks"]}
    assert state["ibkr_yahoo_historical_ohlcv_agreement"]["passed"] is False
    assert state["ibkr_yahoo_historical_ohlcv_agreement"]["observed"]==100
    assert report["independent_source_approval"] is False
    assert report["trading_enabled"] is False


def test_ibkr_crosscheck_inconsistent_count_fails_closed():
    i,p,l,sec=fixtures()
    with pytest.raises(MachineEvidenceUnavailable):
        project_machine_qa(i,p,sec,
            ibkr_audit={"compared":101,"agreed":100,"conflicts":2})
