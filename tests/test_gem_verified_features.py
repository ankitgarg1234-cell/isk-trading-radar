"""GEM source features recomputed from actual bars and original 10-Qs."""
from datetime import date, timedelta
from gem_data.gem_source_feature_verifier import (
    verify_financial_features, verify_price_features, recompute_full_month)
from gem_data.gem_monthly_signal import FROZEN


def six_facts():
    rows={}
    for key, value in (("revenue_now",130.), ("revenue_prior",100.),
                       ("income_now",25.), ("income_prior",10.),
                       ("operating_now",20.), ("operating_prior",10.)):
        is_now=key.endswith("now")
        rows[key]={"form":"10-Q","unit":"USD","source_context_reviewed":True,
                   "accession":"0000123456-25-000001" if is_now else "0000123456-24-000001",
                   "period_start":"2025-04-01" if is_now else "2024-04-01",
                   "period_end":"2025-06-30" if is_now else "2024-06-30",
                   "filed":"2025-07-20" if is_now else "2024-07-20",
                   "accepted_at":"2025-07-20T14:00:00Z" if is_now else "2024-07-20T14:00:00Z",
                   "value":value}
    return rows


def test_financials_derive_earnings_and_margin_not_trust_prefilled_score():
    report=verify_financial_features(six_facts(),signal_day="2025-09-30")
    assert abs(report["revenue_yoy"]-.3)<.00001
    assert report["earnings_improvement"] is True
    assert report["margin_delta_pp"]>3


def test_real_bar_math_recovers_63_session_return_and_adv():
    days=[(date(2025,9,30)-timedelta(days=126-i)).isoformat()
          for i in range(127)]
    price={"adjustment_basis":"FROZEN_VERIFIED",
           "bars":[{"session":day,"frozen_close":100+i,
                    "nominal_close":100+i,"volume":1000000}
                   for i,day in enumerate(days)]}
    results=verify_price_features(price,signal_day=days[-1],sessions=days)
    assert abs(results["r63"] - (226/163-1))<1e-12
    assert results["adv20"]>100000000


def test_month_recomputed_and_less_than_five_qualified_remain_eligible():
    days=[(date(2025,9,30)-timedelta(days=126-i)).isoformat()
          for i in range(127)]
    price={"adjustment_basis":"FROZEN_VERIFIED",
           "bars":[{"session":day,"frozen_close":100+i,
                    "nominal_close":100+i,"volume":1000000}
                   for i,day in enumerate(days)]}
    members=[{"security_id":str(i),"ticker":sym}
             for i,sym in enumerate(("A","B"))]
    rows=[{"security_id":m["security_id"],"ticker":m["ticker"],
           "prices":price,"facts":six_facts(),"identity_reviewed":True}
          for m in members]
    snapshot={"schema":"gem-source-month-v1","universe":members,"candidates":rows,
              "completed_sessions":days,"signal_session":days[-1],
              "next_session":"2025-10-01","calendar_verified":True,
              "membership_reviewed":True,"actions_reviewed":True,
              "benchmark_reviewed":True,"source_manifest_reviewed":True}
    report=recompute_full_month(snapshot,fixture_min_members=2)
    assert report["raw_sources_used"] is True
    assert report["data_status"]=="REVIEWED_COMPLETE"
    assert report["selected"]==["A","B"]
    assert report["broker_orders_sent"] == 0
    rows[0]["prices"]["bars"].pop()
    held=recompute_full_month(snapshot,fixture_min_members=2)
    assert held["data_status"]=="HOLD"
    assert held["selected"]==[]
    assert held["independent_recalculation_blockers"][0]["ticker"]=="A"
