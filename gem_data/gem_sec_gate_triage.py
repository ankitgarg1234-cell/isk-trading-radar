"""Fail-closed preliminary GEM SEC quarterly revenue screen.

A deterministic pre-screen can prioritize companies whose original 10-Q
direct-quarter source candidates appear to fail revenue growth >20%.
This is NOT independent context certification and NEVER removes a security
from GEM's required point-in-time candidate universe.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ACC = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_KEY="STANDARD_REVENUE"
_MAX=Decimal("1e18")


def preliminary_revenue_gate(document, *, as_of):
    """Return source-linked provisional verdict or a bounded hold.

    A single value is not sufficient unless BOTH original 10-Q quarters
    have unambiguous undimensioned USD values, separate original SHA256,
    independent filing accessions and corresponding report periods.
    """
    hold={"status":"CANNOT_DETERMINE_FROM_ORIGINAL_QUARTERS",
          "revenue_growth_pct_candidate":None,
          "provisional_revenue_gate_fail":False,
          "eligible_for_ranking":False,
          "financial_ineligibility_certified":False}
    if not isinstance(document,dict):
        return hold
    try:
        cutoff=date.fromisoformat(as_of)
        rows=[]
        for label in ("current","prior"):
            row=document[label]
            if not isinstance(row,dict):
                return hold
            if not _SHA.fullmatch(str(row.get("original_raw_sha256",""))):
                return hold
            if not _ACC.fullmatch(str(row.get("accession",""))):
                return hold
            if _KEY in (row.get("ambiguous_standard_concepts") or []):
                return hold
            data=row.get("standard_unique_values")
            if not isinstance(data,dict):
                return hold
            values=data.get(_KEY)
            if not isinstance(values,list) or len(values)!=1:
                return hold
            value=Decimal(str(values[0]))
            if not value.is_finite() or value<=0 or value>_MAX:
                return hold
            period=date.fromisoformat(row["period_end"])
            if period>cutoff:
                return hold
            rows.append((row["accession"],period,value,row["original_raw_sha256"]))
        current,prior=rows
        days=(current[1]-prior[1]).days
        if not 310<=days<=420 or current[0]==prior[0]:
            return hold
        result=(current[2]/prior[2]-Decimal(1))*100
        return {
          "status":("PRELIMINARY_REVENUE_GATE_FAIL_NEEDS_SOURCE_QA" if result<=20
                    else "PRELIMINARY_REVENUE_GATE_PASS_OTHER_GATES_UNKNOWN"),
          "revenue_growth_pct_candidate":round(float(result),5),
          "provisional_revenue_gate_fail":bool(result<=20),
          "current_accession":current[0],"prior_accession":prior[0],
          "current_original_sha256":current[3],"prior_original_sha256":prior[3],
          "current_period_end":current[1].isoformat(),
          "prior_period_end":prior[1].isoformat(),
          "eligible_for_ranking":False,
          "financial_ineligibility_certified":False,
        }
    except (ValueError,TypeError,KeyError,InvalidOperation,OverflowError,ZeroDivisionError):
        return hold
