"""SEC remediation output classifications, no premature approval."""
from gem_data.sec_review_state_model import classify_candidate


def test_original_10q_six_fact_candidates_are_not_certified():
    assert classify_candidate(True,False,False) == "SIX_FACT_CANDIDATES_NOT_CERTIFIED"


def test_conflicting_original_contexts_precede_alias_mapping():
    assert classify_candidate(False,True,True) == "CONFLICTING_FACT_CONTEXTS_NEED_REVIEW"


def test_issuer_specific_financials_stay_manual_review():
    assert classify_candidate(False,True,False) == "ACCOUNTING_DEFINITIONS_NEED_MAPPING"


def test_missing_original_quarter_facts_stay_open():
    assert classify_candidate(False,False,False) == "QUARTERLY_FACTS_MISSING"
