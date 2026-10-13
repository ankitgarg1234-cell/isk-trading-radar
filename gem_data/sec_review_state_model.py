"""Classify source evidence, without automatically certifying GEM financial factors."""


def classify_candidate(complete: bool, alternative: bool, conflicting: bool) -> str:
    if complete:
        return 'SIX_FACT_CANDIDATES_NOT_CERTIFIED'
    if conflicting:
        return 'CONFLICTING_FACT_CONTEXTS_NEED_REVIEW'
    if alternative:
        return 'ACCOUNTING_DEFINITIONS_NEED_MAPPING'
    return 'QUARTERLY_FACTS_MISSING'
