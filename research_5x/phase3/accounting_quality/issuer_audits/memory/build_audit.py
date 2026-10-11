"""Rebuild source-reviewed MU/STX/WDC accounting bridges, without outcome fitting.

All amounts are USD millions. Input facts are manually transcribed from original
issuer releases and accession documents named below. Rebuilding is offline;
the source-document retention manifest is maintained separately. Missingness
and economic scope are inputs, never inferred from favorable outcomes.
"""
from __future__ import annotations
import csv
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIOR = ROOT / "research_5x/phase2/2026-10-11_earnings_acceleration/sources"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_csv(path, rows):
    fields = sorted(set().union(*(r.keys() for r in rows))) if rows else []
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)

def mu_release(year, quarter, published):
    name = {2:"Second-Quarter",3:"Third-Quarter",4:"Fourth-Quarter-and-Full-Year"}[quarter]
    slug_date=date.fromisoformat(published).strftime("%m-%d-%Y")
    return f"https://investors.micron.com/news/press-release/{published[:4]}/Micron-Technology-Inc--Reports-Results-for-the-{name}-of-Fiscal-{year}-{slug_date}/default.aspx"

def stx_release(year):
    return f"https://investors.seagate.com/news/news-details/{year}/Seagate-Technology-Reports-Fiscal-Fourth-Quarter-and-Fiscal-Year-{year}-Financial-Results/default.aspx"

SOURCES = [
    dict(source_id="MU-Q4-2023-ORIGINAL", ticker="MU", source_type="original_earnings_release", published="2023-09-27", url=mu_release(2023,4,"2023-09-27"), period_end="2023-08-31", reviewed="Q4/annual income, gross-capex/adjusted-FCF reconciliation, inventory NRV note", scope="consolidated", accepted_et=None, accession=None),
    dict(source_id="MU-Q4-2024-ORIGINAL", ticker="MU", source_type="original_earnings_release", published="2024-09-25", url=mu_release(2024,4,"2024-09-25"), period_end="2024-08-29", reviewed="Q4/annual income and gross-capex/adjusted-FCF reconciliation", scope="consolidated", accepted_et=None, accession=None),
    dict(source_id="MU-Q2-2024-ORIGINAL", ticker="MU", source_type="original_earnings_release", published="2024-03-20", url=mu_release(2024,2,"2024-03-20"), period_end="2024-02-29", reviewed="Income, GAAP-adjusted bridge, cash reconciliation, NRV/patent/tax notes", scope="consolidated", accepted_et=None, accession=None),
    dict(source_id="MU-Q3-2025-ORIGINAL", ticker="MU", source_type="original_earnings_release", published="2025-06-25", url=mu_release(2025,3,"2025-06-25"), period_end="2025-05-29", reviewed="Income, GAAP-adjusted bridge, gross capex and adjusted cash reconciliation", scope="consolidated", accepted_et=None, accession=None),
    dict(source_id="MU-FY2023-10K", ticker="MU", source_type="original_10K", published="2023-10-06", url="https://www.sec.gov/Archives/edgar/data/723125/000072312523000054/mu-20230831.htm", period_end="2023-08-31", reviewed="Annual income/cash-flow totals and inventory note; targeted reconciliation", scope="consolidated", accepted_et="2023-10-06 16:01:37", accession="0000723125-23-000054", submissions_raw_utc="2023-10-07T00:01:37.000Z"),
    dict(source_id="MU-FY2024-10K", ticker="MU", source_type="original_10K", published="2024-10-04", url="https://www.sec.gov/Archives/edgar/data/723125/000072312524000027/mu-20240829.htm", period_end="2024-08-29", reviewed="Annual income/cash-flow totals, working-capital and inventory NRV bridge", scope="consolidated", accepted_et="2024-10-04 16:12:50", accession="0000723125-24-000027", submissions_raw_utc="2024-10-05T00:12:50.000Z"),
    dict(source_id="STX-Q4-2023-ORIGINAL", ticker="STX", source_type="original_earnings_release", published="2023-07-26", url=stx_release(2023), period_end="2023-06-30", reviewed="Q4/annual income and CFO/gross-capex/FCF reconciliation", scope="consolidated", accepted_et=None, accession=None),
    dict(source_id="STX-Q4-2024-ORIGINAL", ticker="STX", source_type="original_earnings_release", published="2024-07-23", url=stx_release(2024), period_end="2024-06-28", reviewed="Q4/annual statements, divestiture gain/cash classification, GAAP-adjusted bridge", scope="consolidated", accepted_et=None, accession=None),
    dict(source_id="STX-FY2023-10K", ticker="STX", source_type="original_10K", published="2023-08-04", url="https://www.sec.gov/Archives/edgar/data/1137789/000113778923000049/stx-20230630.htm", period_end="2023-06-30", reviewed="Annual income/CFO/capex, working-capital drivers; targeted reconciliation", scope="consolidated", accepted_et="2023-08-04 16:27:43", accession="0001137789-23-000049", submissions_raw_utc="2023-08-04T20:27:43.000Z"),
    dict(source_id="STX-FY2024-10K", ticker="STX", source_type="original_10K", published="2024-08-02", url="https://www.sec.gov/Archives/edgar/data/1137789/000113778924000068/stx-20240628.htm", period_end="2024-06-28", reviewed="Annual income/CFO/capex, Note18 divestiture, working capital, interest, BIS cash", scope="consolidated", accepted_et="2024-08-02 16:20:12", accession="0001137789-24-000068", submissions_raw_utc="2024-08-02T20:20:12.000Z"),
    dict(source_id="WDC-Q4-2024-ORIGINAL", ticker="WDC", source_type="original_earnings_release", published="2024-07-31", url="https://investor.wdc.com/news-releases/news-release-details/western-digital-reports-fiscal-fourth-quarter-and-fiscal-year-1", period_end="2024-06-28", reviewed="Preliminary Q4/annual income/cash, segment bridge and company-defined FCF", scope="HDD_plus_Flash_combined", accepted_et=None, accession=None),
    dict(source_id="WDC-FY2024-10K", ticker="WDC", source_type="original_10K", published="2024-08-20", url="https://www.sec.gov/Archives/edgar/data/106040/000010604024000031/wdc-20240628.htm", period_end="2024-06-28", reviewed="Original annual income, litigation291m, gross/net capex and CFO", scope="HDD_plus_Flash_combined", accepted_et="2024-08-19 17:39:43", accession="0000106040-24-000031", submissions_raw_utc="2024-08-20T01:39:43.000Z"),
    dict(source_id="WDC-Q3-2025-ORIGINAL", ticker="WDC", source_type="original_earnings_release", published="2025-04-30", url="https://investor.wdc.com/node/26681", period_end="2025-03-28", reviewed="Continuing income/GAAP-adjusted bridge, consolidated cash and FCF scope footnote", scope="HDD_continuing_income_but_consolidated_cash", accepted_et=None, accession=None),
    dict(source_id="WDC-Q3-2025-10Q", ticker="WDC", source_type="original_10Q", published="2025-05-02", url="https://www.sec.gov/Archives/edgar/data/106040/000010604025000026/wdc-20250328.htm", period_end="2025-03-28", reviewed="Income, Note3 discontinued scope, selected discontinued capex/SBC but no segregated CFO", scope="HDD_continuing_income_but_consolidated_cash", accepted_et="2025-05-02 16:34:25", accession="0000106040-25-000026"),
]

ROWS = [
    dict(source_id="MU-Q4-2023-ORIGINAL",ticker="MU",period="FY2023Q4",period_end="2023-08-31",period_type="quarter",revenue=4010,gross_profit=-435,oi=-1472,ni=-1430,adjusted_oi=-1208,adjusted_ni=-1177,cfo=249,gross_ppe_capex=1461,equipment_contract_payments=26,ppe_sale_proceeds=18,capital_funding=462,company_fcf=-758,sbc_oi_bridge=151,inventory_lower_cost=563,inventory_charge=0,interest_expense=129,eps_gaap=-1.31,eps_adjusted=-1.07,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Amounts funded by partners (original release label; do not silently rename)"),
    dict(source_id="MU-Q4-2023-ORIGINAL",ticker="MU",period="FY2023",period_end="2023-08-31",period_type="annual",revenue=15540,gross_profit=-1416,oi=-5745,ni=-5833,adjusted_oi=-4819,adjusted_ni=-4862,cfo=1559,gross_ppe_capex=7676,equipment_contract_payments=138,ppe_sale_proceeds=92,capital_funding=710,company_fcf=-5453,sbc_oi_bridge=564,sbc_cash_flow=596,inventory_lower_cost=844,inventory_charge=1831,interest_expense=388,eps_gaap=-5.34,eps_adjusted=-4.45,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Amounts funded by partners (original release)"),
    dict(source_id="MU-FY2023-10K",ticker="MU",period="FY2023",period_end="2023-08-31",period_type="annual",revenue=15540,gross_profit=-1416,oi=-5745,ni=-5833,cfo=1559,gross_ppe_capex=7676,equipment_contract_payments=138,capital_funding=710,sbc_cash_flow=596,inventory_lower_cost=844,inventory_charge=1831,interest_expense=388,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Government incentives (annual cash-flow statement)"),
    dict(source_id="MU-Q2-2024-ORIGINAL",ticker="MU",period="FY2024Q2",period_end="2024-02-29",period_type="quarter",revenue=5824,gross_profit=1079,oi=191,ni=793,adjusted_oi=204,adjusted_ni=476,cfo=1219,gross_ppe_capex=1384,equipment_contract_payments=26,ppe_sale_proceeds=13,capital_funding=149,company_fcf=-29,sbc_oi_bridge=209,inventory_lower_cost=382,inventory_charge=0,operating_patent_gain=200,ni_tax_adjustment=-328,eps_gaap=.71,eps_adjusted=.42,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Government incentives"),
    dict(source_id="MU-Q4-2024-ORIGINAL",ticker="MU",period="FY2024Q4",period_end="2024-08-29",period_type="quarter",revenue=7750,gross_profit=2737,oi=1522,ni=887,adjusted_oi=1745,adjusted_ni=1342,cfo=3405,gross_ppe_capex=3120,equipment_contract_payments=22,ppe_sale_proceeds=12,capital_funding=48,company_fcf=323,sbc_oi_bridge=213,eps_gaap=.79,eps_adjusted=1.18,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Government incentives"),
    dict(source_id="MU-Q4-2024-ORIGINAL",ticker="MU",period="FY2024",period_end="2024-08-29",period_type="annual",revenue=25111,gross_profit=5613,oi=1304,ni=778,adjusted_oi=1935,adjusted_ni=1472,cfo=8507,gross_ppe_capex=8386,equipment_contract_payments=149,ppe_sale_proceeds=99,capital_funding=315,company_fcf=386,sbc_cash_flow=833,eps_gaap=.70,eps_adjusted=1.30,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Government incentives"),
    dict(source_id="MU-FY2024-10K",ticker="MU",period="FY2024",period_end="2024-08-29",period_type="annual",revenue=25111,gross_profit=5613,oi=1304,ni=778,cfo=8507,gross_ppe_capex=8386,equipment_contract_payments=149,capital_funding=315,sbc_cash_flow=833,inventory_lower_cost=987,inventory_charge=0,cf_receivables=-3581,cf_inventories=-488,cf_accounts_payable_accrued=1915,cf_other_current_liabilities=989,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Government incentives"),
    dict(source_id="MU-Q3-2025-ORIGINAL",ticker="MU",period="FY2025Q3",period_end="2025-05-29",period_type="quarter",revenue=9301,gross_profit=3508,oi=2169,ni=1885,adjusted_oi=2490,adjusted_ni=2181,cfo=4609,gross_ppe_capex=2938,equipment_contract_payments=0,ppe_sale_proceeds=12,capital_funding=266,company_fcf=1949,sbc_oi_bridge=263,operating_patent_charge=57,interest_expense=123,ni_tax_adjustment=-71,eps_gaap=1.68,eps_adjusted=1.91,income_scope="consolidated",cash_scope="consolidated",capital_funding_label="Government incentives"),
    dict(source_id="STX-Q4-2023-ORIGINAL",ticker="STX",period="FY2023Q4",period_end="2023-06-30",period_type="quarter",revenue=1602,oi=26,ni=-92,adjusted_oi=55,adjusted_ni=-37,cfo=218,gross_ppe_capex=50,company_fcf=168,sbc_oi_bridge=22,income_scope="consolidated",cash_scope="consolidated"),
    dict(source_id="STX-Q4-2023-ORIGINAL",ticker="STX",period="FY2023",period_end="2023-06-30",period_type="annual",revenue=7384,oi=-342,ni=-529,adjusted_ni=40,cfo=942,gross_ppe_capex=316,company_fcf=626,sbc_cash_flow=115,bis_expense=300,cf_receivables=911,cf_inventories=425,cf_accounts_payable=-421,income_scope="consolidated",cash_scope="consolidated"),
    dict(source_id="STX-FY2023-10K",ticker="STX",period="FY2023",period_end="2023-06-30",period_type="annual",revenue=7384,oi=-342,ni=-529,cfo=942,gross_ppe_capex=316,sbc_cash_flow=115,bis_expense=300,cf_receivables=911,cf_inventories=425,cf_accounts_payable=-421,swap_cash_receipts=110,income_scope="consolidated",cash_scope="consolidated"),
    dict(source_id="STX-Q4-2024-ORIGINAL",ticker="STX",period="FY2024Q4",period_end="2024-06-28",period_type="quarter",revenue=1887,oi=314,ni=513,adjusted_oi=327,adjusted_ni=222,cfo=434,gross_ppe_capex=54,company_fcf=380,sbc_oi_bridge=38,nonoperating_divestiture_gain=313,divestiture_cfo_receipts=226,purchase_order_cancellation_credit=26,restructuring_credit=3,interest_expense=82,eps_gaap=2.39,eps_adjusted=1.05,income_scope="consolidated",cash_scope="consolidated"),
    dict(source_id="STX-Q4-2024-ORIGINAL",ticker="STX",period="FY2024",period_end="2024-06-28",period_type="annual",revenue=6551,oi=452,ni=335,adjusted_ni=272,cfo=918,gross_ppe_capex=254,company_fcf=664,sbc_cash_flow=127,nonoperating_divestiture_gain=313,divestiture_cfo_receipts=226,divestiture_investing_receipts=326,divestiture_total_gross_cash=560,interest_expense=332,bis_cash_paid=45,cf_receivables=192,cf_inventories=-99,cf_accounts_payable=227,cf_other_assets_liabilities=243,eps_gaap=1.58,eps_adjusted=1.29,income_scope="consolidated",cash_scope="consolidated"),
    dict(source_id="STX-FY2024-10K",ticker="STX",period="FY2024",period_end="2024-06-28",period_type="annual",revenue=6551,oi=452,ni=335,cfo=918,gross_ppe_capex=254,sbc_cash_flow=127,nonoperating_divestiture_gain=313,divestiture_cfo_receipts=226,divestiture_investing_receipts=326,interest_expense=332,bis_cash_paid=45,cf_receivables=192,cf_inventories=-99,cf_accounts_payable=227,cf_other_assets_liabilities=243,swap_cash_receipts=25,income_scope="consolidated",cash_scope="consolidated"),
    dict(source_id="WDC-Q4-2024-ORIGINAL",ticker="WDC",period="FY2024Q4",period_end="2024-06-28",period_type="quarter",revenue=3764,gross_profit=1353,oi=507,ni=330,adjusted_oi=666,adjusted_ni=535,cfo=366,net_ppe_capex=116,flash_ventures_net_receipts=32,company_fcf=282,sbc_oi_bridge=69,eps_gaap=.88,eps_adjusted=1.44,income_scope="HDD_plus_Flash_combined",cash_scope="HDD_plus_Flash_combined"),
    dict(source_id="WDC-Q4-2024-ORIGINAL",ticker="WDC",period="FY2024",period_end="2024-06-28",period_type="annual",revenue=13003,gross_profit=2945,oi=-26,ni=-507,cfo=-294,net_ppe_capex=292,flash_ventures_net_receipts=239,company_fcf=-347,sbc_oi_bridge=295,income_scope="HDD_plus_Flash_combined",cash_scope="HDD_plus_Flash_combined"),
    dict(source_id="WDC-FY2024-10K",ticker="WDC",period="FY2024",period_end="2024-06-28",period_type="annual",revenue=13003,gross_profit=2945,oi=-317,ni=-798,cfo=-294,gross_ppe_capex=487,ppe_sale_proceeds=195,flash_ventures_net_receipts=239,operating_litigation_charge=291,interest_expense=417,income_scope="HDD_plus_Flash_combined",cash_scope="HDD_plus_Flash_combined"),
    dict(source_id="WDC-Q3-2025-ORIGINAL",ticker="WDC",period="FY2025Q3",period_end="2025-03-28",period_type="quarter",revenue=2294,gross_profit=912,oi=760,ni=772,consolidated_ni=520,discontinued_ni=-252,adjusted_oi=596,adjusted_ni=500,cfo=508,net_ppe_capex=128,flash_ventures_net_receipts=56,company_fcf=436,sbc_oi_bridge=35,operating_litigation_credit=201,tax_benefit=698,nonoperating_sandisk_mark_loss=606,eps_gaap=2.11,eps_adjusted=1.36,income_scope="HDD_continuing",cash_scope="combined_including_Flash_to_2025-02-21"),
]

def normalize(row):
    r = dict(row)
    src = next(s for s in SOURCES if s["source_id"] == r["source_id"])
    r.update(source_url=src["url"], source_published_date=src["published"],
             conservative_available_calendar_date=(date.fromisoformat(src["published"])+timedelta(days=1)).isoformat(),
             currency="USD", monetary_units="millions", reported_evidence_label="fact_source_reported",
             adjusted_evidence_label="management_adjusted", analyst_evidence_label="derived_calculation",
             confidence="high_for_transcribed_facts_not_predictive_validation")
    same_scope = r["income_scope"] == r["cash_scope"]
    rev, ni = r["revenue"], r["ni"]
    r["cash_income_scope_comparable"] = same_scope
    r["gaap_operating_margin_pct"] = 100*r["oi"]/rev
    r["gross_ppe_capex_missing_reason"] = None if "gross_ppe_capex" in r else "missing_gross_ppe_source_net_ppe_not_substituted"
    fcf = r["cfo"]-r["gross_ppe_capex"] if "gross_ppe_capex" in r else None
    r["analyst_fcf_gross_ppe"] = fcf
    r["analyst_fcf_including_equipment_contracts"] = fcf-r["equipment_contract_payments"] if fcf is not None and "equipment_contract_payments" in r else None
    r["company_fcf_minus_analyst_fcf"] = r["company_fcf"]-fcf if "company_fcf" in r and fcf is not None else None
    r["cfo_ni"] = r["cfo"]/ni if same_scope and ni>0 else None
    r["analyst_fcf_ni"] = fcf/ni if same_scope and ni>0 and fcf is not None else None
    r["cfo_revenue_pct"] = 100*r["cfo"]/rev if same_scope else None
    r["analyst_fcf_revenue_pct"] = 100*fcf/rev if same_scope and fcf is not None else None
    r["gross_capex_revenue_pct"] = 100*r["gross_ppe_capex"]/rev if same_scope and "gross_ppe_capex" in r else None
    r["accrual_proxy_ni_minus_cfo_revenue"] = (ni-r["cfo"])/rev if same_scope else None
    r["cash_ratio_missing_reason"] = "cash_income_economic_scope_mismatch" if not same_scope else ("nonpositive_ni_denominator" if ni<=0 else None)
    for field in ["sbc_cash_flow", "sbc_oi_bridge"]:
        r[field+"_revenue_pct"] = 100*r[field]/rev if field in r else None
    if "divestiture_cfo_receipts" in r:
        r["analyst_cfo_ex_divestiture_receipts"] = r["cfo"]-r["divestiture_cfo_receipts"]
        r["analyst_fcf_ex_divestiture_receipts"] = fcf-r["divestiture_cfo_receipts"] if fcf is not None else None
    if r["period"]=="FY2024Q2" and r["ticker"]=="MU":
        r["analyst_oi_ex_patent_gain"] = r["oi"]-r["operating_patent_gain"]
        r["analyst_oi_ex_patent_and_inventory_lower_cost"] = r["oi"]-r["operating_patent_gain"]-r["inventory_lower_cost"]
        r["analyst_adjusted_oi_ex_inventory_lower_cost"] = r["adjusted_oi"]-r["inventory_lower_cost"]
    if "operating_litigation_credit" in r:
        r["analyst_oi_ex_litigation_credit"] = r["oi"]-r["operating_litigation_credit"]
        r["analyst_operating_margin_ex_litigation_pct"] = 100*r["analyst_oi_ex_litigation_credit"]/rev
    return r

def build():
    HERE.mkdir(parents=True,exist_ok=True)
    manifest_path=HERE/"download_manifest.json"
    retained={r["source_id"]:r for r in json.loads(manifest_path.read_text())["snapshots"]} if manifest_path.exists() else {}
    source_rows=[]
    conflicts=[]
    for s in SOURCES:
        s=dict(s)
        s["retrieved_client_date"]="2026-10-11"
        s["review_status"]="manual_primary_web_review_targeted_sections"
        raw=retained.get(s["source_id"],{})
        s["original_document_binary_retained"] = raw.get("status","").startswith("retained")
        s["raw_snapshot_path"] = raw.get("path")
        s["raw_snapshot_uncompressed_sha256"] = raw.get("uncompressed_sha256")
        s["binary_retention_limitation"]="Current snapshot of dated original page/accession, not a historical web archive; see download_manifest.json for download failures"
        if s["accession"]:
            cik={"MU":723125,"STX":1137789,"WDC":106040}[s["ticker"]]
            s["index_url"]=f"https://www.sec.gov/Archives/edgar/data/{cik}/{s['accession'].replace('-','')}/{s['accession']}-index.htm"
            et=datetime.strptime(s["accepted_et"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("America/New_York"))
            s["accepted_utc_from_original_index"]=et.astimezone(ZoneInfo("UTC")).isoformat()
            raw=s.get("submissions_raw_utc")
            if raw:
                api=datetime.fromisoformat(raw.replace("Z","+00:00"))
                delta=(api-et).total_seconds()
                s["submissions_minus_index_seconds"]=delta
                if delta:
                    conflicts.append(dict(ticker=s["ticker"],source_id=s["source_id"],accession=s["accession"],submissions_raw_utc=raw,index_accepted_eastern=s["accepted_et"],index_accepted_utc=s["accepted_utc_from_original_index"],difference_seconds=delta,treatment="Original accession index controls; preserve raw API and require index verification",source_url=s["index_url"]))
        source_rows.append(s)
    normalized=[normalize(r) for r in ROWS]
    write_csv(HERE/"quality_metrics.csv",normalized)
    write_csv(HERE/"source_lineage.csv",source_rows)
    write_csv(HERE/"timestamp_conflicts.csv",conflicts)
    prior=[]
    for sub in ("memory","wdc"):
        for p in sorted((PRIOR/sub).glob("*")):
            if p.is_file():prior.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p)))
    inherited=json.loads((PRIOR/"memory/source_evidence.json").read_text())
    wdc=json.loads((PRIOR/"wdc/source_evidence.json").read_text())
    inherited_rows=[]
    for r in inherited["quarter_timeline"]:
        inherited_rows.append(dict(ticker=r["ticker"],period=r["fiscal_quarter"],period_end=r["period_end"],release_date=r["release_date"],source_url=r["source_url"],source_id=r["source_id"],evidence_status="phase2_manual_release_review_inherited_not_new_independent_validation",quality_flags=r["quality_flags"]))
    for r in wdc["quarters"]:
        inherited_rows.append(dict(ticker="WDC",period=r["fiscal_quarter"],period_end=r["period_end"],release_date=r["release_date"],source_url=r["release_url"],source_id=r["source_id"],evidence_status="phase2_manual_release_review_inherited_not_new_independent_validation",quality_flags=r["qa_notes"]))
    write_csv(HERE/"inherited_release_inventory.csv",inherited_rows)
    evidence=dict(schema="phase3_memory_accounting_audit_v1",asof_client_date="2026-10-11",units="USD millions except ratios/EPS",scope="Mandatory three-issuer source audits only; no cohort discrimination or policy backtest",sources=source_rows,reported_rows=ROWS,normalized_rows=normalized,timestamp_conflicts=conflicts,prior_files_readonly_hashes=prior,
                  missingness="Absent fields mean missing source/coverage, never zero. Explicit zero exists only when the primary table explicitly prints a dash or zero in the stated period.",
                  normalization_notes=["GAAP and issuer-adjusted values are separate", "MU CFO minus gross PPE differs from adjusted FCF, which also includes contract payments, PPE sales and capital funding", "MU cash-flow SBC includes capitalized/accounting effects and differs from OI bridge SBC; neither silently replaces the other", "STX analyst CFO/FCF ex divestiture receipts is a diagnostic, not a complete recurring-cash definition", "WDC quarter2025Q3 standalone HDD cash/revenue/NI ratios are missing; raw consolidated CFO remains visible", "An original annual-filed value cannot replace earlier preliminary Q4 release before filing eligibility"],
                  certification_limit="Targeted manual primary-source reviews of these facts; no assertion of full financial-statement audit or certified index membership. Cannot pass broad ExperimentA Gate1 by themselves.")
    (HERE/"source_evidence.json").write_text(json.dumps(evidence,indent=2)+"\n")
    checks=[]
    def ck(label,actual,expected):
        ok=abs(actual-expected)<1e-9
        checks.append(dict(check=label,actual=actual,expected=expected,passed=ok))
        assert ok,(label,actual,expected)
    for r in ROWS:
        if r["ticker"]=="MU" and "company_fcf" in r:
            calc=r["cfo"]-r["gross_ppe_capex"]-r["equipment_contract_payments"]+r["ppe_sale_proceeds"]+r["capital_funding"]
            ck(f"{r['source_id']}/{r['period']} company-adjusted cash bridge",calc,r["company_fcf"])
        if r["ticker"]=="STX" and "company_fcf" in r:
            ck(f"{r['source_id']}/{r['period']} reported CFO less gross capex",r["cfo"]-r["gross_ppe_capex"],r["company_fcf"])
        if r["ticker"]=="WDC" and "company_fcf" in r:
            ck(f"{r['source_id']}/{r['period']} company-FCF net-capex plusFlash bridge",r["cfo"]-r["net_ppe_capex"]+r["flash_ventures_net_receipts"],r["company_fcf"])
    for t,y in (("MU",2023),("MU",2024),("STX",2023),("STX",2024)):
        release=next(r for r in ROWS if r["ticker"]==t and r["period"]==f"FY{y}" and "ORIGINAL" in r["source_id"])
        filing=next(r for r in ROWS if r["ticker"]==t and r["period"]==f"FY{y}" and "10K" in r["source_id"])
        for field in ("revenue","oi","ni","cfo","gross_ppe_capex"):
            ck(f"{t}FY{y} original release-to-original annual {field}",release[field],filing[field])
    for field,values in dict(revenue=[4726,5824,6811,7750],oi=[-1128,191,719,1522],ni=[-1234,793,332,887],cfo=[1401,1219,2482,3405],gross_ppe_capex=[1796,1384,2086,3120]).items():
        annual=next(r for r in ROWS if r["source_id"]=="MU-FY2024-10K")
        ck(f"MU FY2024 four observable quarter sums:{field}",sum(values),annual[field])
    for field,values in dict(revenue=[1454,1555,1655,1887],oi=[-129,124,143,314],ni=[-184,-19,25,513],cfo=[127,169,188,434],gross_ppe_capex=[70,70,60,54]).items():
        annual=next(r for r in ROWS if r["source_id"]=="STX-FY2024-10K")
        ck(f"STX FY2024 four observable quarter sums:{field}",sum(values),annual[field])
    ck("WDC annual original-preliminary OI less laterlitigation",-26-291,-317)
    ck("WDC annual original-preliminary NI less laterlitigation",-507-291,-798)
    ck("WDC corrected Q4 OI annual-minus9month",-317-(-596-210+273),216)
    ck("WDC corrected Q4 NI annual-minus9month",-798-(-685-287+135),39)
    ck("WDC quarter2025Q3 continuing plus discontinuedNI",772-252,520)
    ck("WDC quarter2025Q3 OI aftercredit/SBC/otheradjustments",760-201+35+2,596)
    ck("MU quarter2024Q2 OI ex patent",191-200,-9)
    ck("MU quarter2024Q2 OI ex patent and inventory benefit",191-200-382,-391)
    ck("MU quarter2024Q2 adjustedOI ex inventory benefit",204-382,-178)
    ck("STX quarter2024Q4 cash afterdivestiturediagnostic",434-226,208)
    ck("STX quarter2024Q4 FCF afterdivestiturediagnostic",380-226,154)
    ck("STX FY2024 cash afterdivestiturediagnostic",918-226,692)
    ck("STX FY2024 FCF afterdivestiturediagnostic",664-226,438)
    ck("Two MU API/index conflicts retained",sum(c["ticker"]=="MU" for c in conflicts),2)
    assert all(r["cfo_ni"] is None and r["cfo_revenue_pct"] is None for r in normalized if r["ticker"]=="WDC" and r["period"]=="FY2025Q3")
    checks.append(dict(check="WDC standalone cash ratios blocked; net capex not gross",passed=True))
    assert len(inherited_rows)==30
    checks.append(dict(check="All30 Phase2 originalrelease references retained with inherited labels",passed=True))
    assert all(r["cfo_ni"] is None for r in normalized if r["ni"]<=0)
    checks.append(dict(check="Nonpositive NI cash-conversion denominator remains missing",passed=True))
    status=dict(status="passed_accounting_arithmetic_and_source_lineage_checks_only",checks=checks,check_count=len(checks),all_passed=all(c["passed"] for c in checks),source_count=len(SOURCES),metric_period_vintage_rows=len(normalized),inherited_original_releases=len(inherited_rows),timestamp_conflict_count=len(conflicts),predictive_validation="not_attempted",limits=["No all-39 cohort source certification from this three-issuer packet", "Original binary retention is separately disclosed", "No causal loss attribution or entry-policy claim", "Q4 original releases retained separately from later annual vintages"])
    (HERE/"verification_checks.json").write_text(json.dumps(status,indent=2)+"\n")
    print(json.dumps({k:status[k] for k in ("status","check_count","source_count","metric_period_vintage_rows","timestamp_conflict_count")}))

if __name__=="__main__":
    build()
