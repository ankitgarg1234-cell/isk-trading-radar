"""Rebuild a manually transcribed primary-source memory/HDD evidence packet.

Only factual numeric extracts and short analytical paraphrases are retained.
No vendor facts are relabelled as verified evidence. Release-day timestamps are
unknown unless explicitly documented: date + one calendar day is a conservative
availability floor, subsequently aligned to a session by the owning workflow.
"""
from pathlib import Path
import csv, datetime as dt, json, math

ROOT = Path(__file__).resolve().parent
MU_BASE = "https://investors.micron.com/news/press-release/"
STX_BASE = "https://investors.seagate.com/news/news-details/"

# quarter, period-end, release-date, revenue, prior-year revenue, prior-quarter
# revenue, GAAP gross margin %, adjusted gross margin %, GAAP OI, adjusted OI,
# GAAP NI, adjusted NI, GAAP diluted EPS, adjusted diluted EPS, CFO, adjusted FCF,
# SBC excluded from operating income, next-quarter revenue midpoint / range,
# next-quarter adjusted EPS midpoint / range, GAAP/adjusted GM guide, URL tail.
MU = [
 ["2023Q2","2023-03-02","2023-03-28",3693,7786,4085,-32.7,-31.4,-2303,-2077,-2312,-2081,-2.12,-1.91,343,-1812,136,3700,200,-1.58,.07,-23,-21,"2023/Micron-Technology-Inc--Reports-Results-for-the-Second-Quarter-of-Fiscal-2023-03-28-2023/default.aspx"],
 ["2023Q3","2023-06-01","2023-06-28",3752,8642,3693,-17.8,-16.1,-1761,-1469,-1896,-1565,-1.73,-1.43,24,-1355,151,3900,200,-1.19,.07,-12.5,-10.5,"2023/Micron-Technology-Inc--Reports-Results-for-the-Third-Quarter-of-Fiscal-2023-06-28-2023/default.aspx"],
 ["2023Q4","2023-08-31","2023-09-27",4010,6643,3752,-10.8,-9.1,-1472,-1208,-1430,-1177,-1.31,-1.07,249,-758,151,4400,200,-1.07,.07,-6,-4,"2023/Micron-Technology-Inc--Reports-Results-for-the-Fourth-Quarter-and-Full-Year-of-Fiscal-2023-09-27-2023/default.aspx"],
 ["2024Q1","2023-11-30","2023-12-20",4726,4085,4010,-.7,.8,-1128,-955,-1234,-1048,-1.12,-.95,1401,-333,182,5300,200,-.28,.07,12,13,"2023/Micron-Technology-Inc--Reports-Results-for-the-First-Quarter-of-Fiscal-2024-12-20-2023/default.aspx"],
 ["2024Q2","2024-02-29","2024-03-20",5824,3693,4726,18.5,20,191,204,793,476,.71,.42,1219,-29,209,6600,200,.45,.07,25.5,26.5,"2024/Micron-Technology-Inc--Reports-Results-for-the-Second-Quarter-of-Fiscal-2024-03-20-2024/default.aspx"],
 ["2024Q3","2024-05-30","2024-06-26",6811,3752,5824,26.9,28.1,719,941,332,702,.30,.62,2482,425,217,7600,200,1.08,.08,33.5,34.5,"2024/Micron-Technology-Inc--Reports-Results-for-the-Third-Quarter-of-Fiscal-2024-06-26-2024/default.aspx"],
 ["2024Q4","2024-08-29","2024-09-25",7750,4010,6811,35.3,36.5,1522,1745,887,1342,.79,1.18,3405,323,213,8700,200,1.74,.08,38.5,39.5,"2024/Micron-Technology-Inc--Reports-Results-for-the-Fourth-Quarter-and-Full-Year-of-Fiscal-2024-09-25-2024/default.aspx"],
 ["2025Q1","2024-11-28","2024-12-18",8709,4726,7750,38.4,39.5,2174,2394,1870,2037,1.67,1.79,3244,112,217,7900,200,1.43,.10,37.5,38.5,"2024/Micron-Technology-Inc--Reports-Results-for-the-First-Quarter-of-Fiscal-2025-12-18-2024/default.aspx"],
 ["2025Q2","2025-02-27","2025-03-20",8053,5824,8709,36.8,37.9,1773,2007,1583,1783,1.41,1.56,3942,857,233,8800,200,1.57,.10,35.5,36.5,"2025/Micron-Technology-Inc--Reports-Results-for-the-Second-Quarter-of-Fiscal-2025-03-20-2025/default.aspx"],
 ["2025Q3","2025-05-29","2025-06-25",9301,6811,8053,37.7,39,2169,2490,1885,2181,1.68,1.91,4609,1949,263,10700,300,2.50,.15,41,42,"2025/Micron-Technology-Inc--Reports-Results-for-the-Third-Quarter-of-Fiscal-2025-06-25-2025/default.aspx"],
]
STX = [
 ["2023Q2","2022-12-30","2023-01-25",1887,3116,2035,13,21.4,-160,109,-33,34,-.16,.16,251,172,33,2000,150,.25,.20,None,None,"2023/Seagate-Technology-Reports-Fiscal-Second-Quarter-2023-Financial-Results/default.aspx"],
 ["2023Q3","2023-03-31","2023-04-20",1860,2802,1887,17.2,18.7,-315,65,-433,-58,-2.09,-.28,228,174,31,1700,150,-.20,.20,None,None,"2023/Seagate-Technology-Reports-Fiscal-Third-Quarter-2023-Financial-Results/"],
 ["2023Q4","2023-06-30","2023-07-26",1602,2628,1860,19,19.5,26,55,-92,-37,-.44,-.18,218,168,22,1550,150,-.16,.20,None,None,"2023/Seagate-Technology-Reports-Fiscal-Fourth-Quarter-and-Fiscal-Year-2023-Financial-Results/default.aspx"],
 ["2024Q1","2023-09-29","2023-10-26",1454,2035,1602,10.2,19.8,-129,40,-184,-46,-.88,-.22,127,57,25,1550,150,-.10,.20,None,None,"2023/Seagate-Technology-Reports-Fiscal-First-Quarter-2024-Financial-Results/default.aspx"],
 ["2024Q2","2023-12-29","2024-01-24",1555,1887,1454,23.3,23.6,124,127,-19,25,-.09,.12,169,99,30,1650,150,.25,.20,None,None,"2024/Seagate-Technology-Reports-Fiscal-Second-Quarter-2024-Financial-Results/default.aspx"],
 ["2024Q3","2024-03-29","2024-04-23",1655,1860,1555,25.7,26.1,143,183,25,71,.12,.33,188,128,34,1850,150,.70,.20,None,None,"2024/Seagate-Technology-Reports-Fiscal-Third-Quarter-2024-Financial-Results/default.aspx"],
 ["2024Q4","2024-06-28","2024-07-23",1887,1602,1655,31.8,30.9,314,327,513,222,2.39,1.05,434,380,38,2100,150,1.40,.20,None,None,"2024/Seagate-Technology-Reports-Fiscal-Fourth-Quarter-and-Fiscal-Year-2024-Financial-Results/default.aspx"],
 ["2025Q1","2024-09-27","2024-10-22",2168,1454,1887,32.9,33.3,403,442,305,337,1.41,1.58,95,27,38,2300,150,1.85,.20,None,None,"2024/Seagate-Technology-Reports-Fiscal-First-Quarter-2025-Financial-Results/default.aspx"],
 ["2025Q2","2024-12-27","2025-01-21",2325,1555,2168,34.9,35.5,488,538,336,433,1.55,2.03,221,150,49,2100,150,1.70,.20,None,None,"2025/Seagate-Technology-Reports-Fiscal-Second-Quarter-2025-Financial-Results/default.aspx"],
 ["2025Q3","2025-03-28","2025-04-29",2160,1655,2325,35.2,36.2,431,507,340,407,1.57,1.90,259,216,54,2400,150,2.40,.20,None,None,"2025/Seagate-Technology-Reports-Fiscal-Third-Quarter-2025-Financial-Results/default.aspx"],
]

FLAGS = {
 "MU2023Q2": "GAAP and adjusted results retain inventory write-downs; $1430m Q2 charge affects apparent trough and future cost basis.",
 "MU2023Q3": "CAC restriction was an explicitly disclosed recovery headwind. Adjusted FCF is -$1355m from the reconciliation, not rounded headline -$1360m.",
 "MU2024Q1": "Margins benefited from $605m lower cost of inventory previously written down; adjusted result excludes SBC but does not remove this benefit.",
 "MU2024Q2": "Gross margin includes $382m inventory cost benefit; GAAP OI includes $200m patent gain; tax-rate catch-up supports GAAP NI. Adjusted NI $476m versus GAAP $793m.",
 "MU2024Q3": "GAAP NI fell sequentially despite rising OI/revenue; tax effects make NI acceleration an imperfect operating signal.",
 "MU2024Q4": "GAAP/adjusted NI divergence includes substantial tax adjustments; capital-intensive adjusted FCF includes net government incentives.",
 "MU2025Q1": "Strong YoY growth coincides with a lower next-quarter revenue/EPS guide; this is changing guide horizon, not a same-quarter downward revision.",
 "MU2025Q2": "Revenue, margins and OI declined sequentially; HBM/data-center strength coexists with broader mix weakness.",
 "MU2025Q3": "Adjusted OI excludes SBC $263m and patent license charge $57m; DRAM/NAND ASP trends differ. Adjusted FCF nets government incentives from capex.",
 "STX2023Q2": "Adjusted OI excludes $108m purchase order cancellation fees, restructuring and impairment items; adjusted profitability masks GAAP loss.",
 "STX2023Q3": "GAAP OI includes $300m BIS settlement penalty, payable over five years. Excluding it exaggerates future YoY GAAP margin recovery as operating leverage.",
 "STX2024Q1": "GAAP margin includes cancellation/underutilization costs; $104m interest-rate-swap gain and debt losses affect NI.",
 "STX2024Q4": "GAAP NI includes $313m divestiture gain; $226m divestiture receipts enter reported CFO and FCF. Simple subtractive cash-flow diagnostic gives CFO208/FCF154, not restated issuer metrics.",
 "STX2025Q3": "Revenue/shipments decreased sequentially; management cites temporary production constraints and seasonality. Filing MD&A percent table shows 21% OI margin inconsistent with 431/2160=19.95%; use dollar ratio/release20.0%.",
}

DRIVERS = {
 "MU2023Q2": "Management expected inventory and supply-demand balance to improve; realized profitability still sharply negative.",
 "MU2023Q3": "Management called a revenue trough and reduced wafer starts toward 30%; CAC restriction delayed expected recovery.",
 "MU2023Q4": "Management expected demand growth and supply discipline to support 2024 recovery and a record 2025 industry market.",
 "MU2024Q1": "Management attributed better results to execution and pricing; expected continued 2024 improvement.",
 "MU2024Q2": "Management reported results above the prior guide range and positioned AI/tight supply as recovery drivers.",
 "MU2024Q3": "Management cited high-margin HBM share gains and record data-center SSD revenue.",
 "MU2024Q4": "Management cited AI-driven DRAM/HBM ramp; data-center SSD quarterly revenue exceeded $1bn.",
 "MU2025Q1": "Data-center products supported strong actuals, but next-quarter guide implied sequential softness.",
 "MU2025Q2": "Management reported HBM revenue above $1bn and data-center revenue triple YoY; projected a record next quarter.",
 "MU2025Q3": "HBM revenue grew nearly50% sequentially; record DRAM revenue coexisted with falling NAND selling prices.",
 "STX2023Q2": "Management expected future recovery and planned a 30+TB HAMR launch; no realized revenue recovery yet.",
 "STX2023Q3": "Management extended expected recovery to late2023 after weaker nearline demand/customer inventory correction.",
 "STX2023Q4": "Management cited China recovery uncertainty, cloud inventory digestion and cautious enterprise spending.",
 "STX2024Q1": "Management described modest U.S.cloud improvement despite a prolonged downcycle.",
 "STX2024Q2": "Management reported emerging cloud-nearline recovery and Mozaic/HAMR launch.",
 "STX2024Q3": "Management attributed sequential growth to cloud demand, cost discipline and price execution.",
 "STX2024Q4": "Management emphasized recovering cloud demand, supply discipline and HAMR roadmap.",
 "STX2025Q1": "28TB nearline ramp and wider HAMR qualification supported product momentum.",
 "STX2025Q2": "Initial HAMR Mozaic ramp to lead cloud customer and samples up to36TB were reported management milestones.",
 "STX2025Q3": "Healthy capacity-storage demand and HAMR ramp supported outlook; production constraints limited realized quarter.",
}

HEADERS = ["ticker","fiscal_quarter","period_end","release_date","conservative_available_date","source_id","source_url","revenue_usd_m","prior_year_revenue_usd_m","prior_quarter_revenue_usd_m","revenue_yoy_pct","revenue_qoq_pct","revenue_yoy_acceleration_pp","gross_margin_gaap_pct","gross_margin_adjusted_pct","operating_income_gaap_usd_m","operating_income_adjusted_usd_m","operating_margin_gaap_pct","operating_margin_adjusted_pct","operating_margin_yoy_change_pp","net_income_gaap_usd_m","net_income_adjusted_usd_m","eps_diluted_gaap_usd","eps_diluted_adjusted_usd","cash_from_operations_usd_m","free_cash_flow_company_adjusted_usd_m","sbc_operating_income_bridge_usd_m","next_quarter_revenue_guide_mid_usd_m","next_quarter_revenue_guide_half_range_usd_m","next_quarter_adjusted_eps_guide_mid_usd","next_quarter_adjusted_eps_guide_half_range_usd","next_quarter_gaap_gm_guide_pct","next_quarter_adjusted_gm_guide_pct","next_quarter_guided_revenue_vs_actual_qoq_pct","actual_revenue_vs_prior_company_guide_mid_pct","actual_adjusted_eps_vs_prior_company_guide_mid_delta_usd","same_quarter_guidance_revision","historical_analyst_consensus","demand_evidence_label","demand_comment","quality_flags"]

rows = []
for ticker, data, base in [("MU",MU,MU_BASE),("STX",STX,STX_BASE)]:
    prior = None
    lookup = {}
    for x in data:
        q, end, release, rev, prevyr, prevq, gm, agm, oi, aoi, ni, ani, eps, aeps, cfo, fcf, sbc, guide, guide_range, epsguide, epsrange, gmguide, agmguide, tail = x
        yoy = (rev/prevyr-1)*100
        om, aom = oi/rev*100, aoi/rev*100
        py_q = str(int(q[:4])-1)+q[4:]
        py = lookup.get(py_q)
        available = (dt.date.fromisoformat(release)+dt.timedelta(days=1)).isoformat()
        vals = [ticker,q,end,release,available,ticker+q,base+tail,rev,prevyr,prevq,yoy,(rev/prevq-1)*100,yoy-prior['revenue_yoy_pct'] if prior else None,gm,agm,oi,aoi,om,aom,om-py['operating_margin_gaap_pct'] if py else None,ni,ani,eps,aeps,cfo,fcf,sbc,guide,guide_range,epsguide,epsrange,gmguide,agmguide,(guide/rev-1)*100,(rev/prior['next_quarter_revenue_guide_mid_usd_m']-1)*100 if prior else None,aeps-prior['next_quarter_adjusted_eps_guide_mid_usd'] if prior else None,"not reconstructed","unavailable","management statement",DRIVERS[ticker+q],FLAGS.get(ticker+q,"SBC excluded from adjusted results; GAAP and adjusted EPS may use different diluted shares.")]
        row = dict(zip(HEADERS,vals))
        assert len(vals)==len(HEADERS)
        assert end<release<available<"2025-06-30"
        assert abs(om-oi/rev*100)<1e-10
        rows.append(row);lookup[q]=row;prior=row

filings = [
 {"source_id":"MU_2025Q3_10Q","ticker":"MU","period_end":"2025-05-29","accession":"0000723125-25-000021","filed_date":"2025-06-26","accepted_eastern":"2025-06-25T18:50:42-04:00","accepted_utc":"2025-06-25T22:50:42+00:00","index_url":"https://www.sec.gov/Archives/edgar/data/723125/000072312525000021/0000723125-25-000021-index.html","document_url":"https://www.sec.gov/Archives/edgar/data/723125/000072312525000021/mu-20250529.htm","verified_facts_usd_m":{"revenue":9301,"gross_profit":3508,"operating_income":2169,"net_income":1885,"DRAM_revenue":7071,"NAND_revenue":2155},"management_MDA":["Sequential DRAM bit shipments up over20%, ASP down low-single-digit range.","Sequential NAND bits up mid20%, ASP down high-single-digit range.","YoY DRAM ASP up mid20%; NAND ASP down low20%.","HBM mix and manufacturing cost reductions improve DRAM margins; NAND margin deteriorates."],"label":"Reported facts and management MD&A; reviewed original filing plus acceptance index"},
 {"source_id":"STX_2025Q3_10Q","ticker":"STX","period_end":"2025-03-28","accession":"0001137789-25-000075","filed_date":"2025-05-02","accepted_eastern":"2025-05-02T16:09:12-04:00","accepted_utc":"2025-05-02T20:09:12+00:00","index_url":"https://www.sec.gov/Archives/edgar/data/1137789/000113778925000075/0001137789-25-000075-index.html","document_url":"https://www.sec.gov/Archives/edgar/data/1137789/000113778925000075/stx-20250328.htm","verified_facts_usd_m":{"revenue":2160,"gross_profit":760,"operating_income":431,"net_income":340},"KPI":{"mass_capacity_exabytes_current_prior_quarter_prior_year":[133,140,88],"total_exabytes_current_prior_quarter_prior_year":[144,151,99],"rounded_HDD_price_per_TB_current_prior_quarter_prior_year":[14,14,15],"mass_capacity_revenue_share_pct_current_prior_quarter_prior_year":[81,81,71]},"management_MDA":["Temporary production supply constraints and typical seasonality lowered sequential revenue.","Higher nearline cloud demand and favorable company pricing actions supported YoY growth."],"label":"Reported facts and management MD&A; reviewed original filing plus acceptance index","quality_flags":["MD&A percent table prints21% current-quarter operating margin; dollar financial statement gives19.95%, consistent with release20.0%. Retain discrepancy."]},
]

evidence = {
 "schema_version":"memory_earnings_evidence_v1","research_date":"2026-10-11","decision_cutoff":"2025-06-29","scope":"All10 successive MU and10 STX quarterly releases dated in2023 through June2025; selected winners, descriptive case studies only.",
 "units":{"amounts":"USD millions","margins":"percent","acceleration":"percentage points","EPS":"USD per diluted share"},
 "availability_policy":"Release dates verified from original issuer pages. Intraday release time not certified for each event; availability begins next calendar date and must be aligned to a trading session. Does not grant access at fiscal period-end. Two decision-relevant filings have SEC acceptance verified.",
 "sources":[{"source_id":r['source_id'],"ticker":r['ticker'],"fiscal_quarter":r['fiscal_quarter'],"release_date":r['release_date'],"url":r['source_url'],"review_status":"Original issuer release manually reviewed; not every filing independently audited","facts":{k:r[k] for k in HEADERS[7:33]},"quality_flags":r['quality_flags']} for r in rows],
 "quarter_timeline":rows,"filing_evidence":filings,
 "formulas":{"revenue_yoy_pct":"100*(quarter revenue / same fiscal quarter prior-year revenue - 1)","revenue_yoy_acceleration_pp":"current revenue YoY % minus prior sequential quarter revenue YoY %","operating_margin":"100*operating income / revenue; uses reported dollar values, not rounded presentation margin","guide_miss_beat":"current actual versus previous release's management guidance for this same quarter, not analyst consensus","guide_sequence":"next-quarter guide versus just-reported actual: changing target quarter, not a same-quarter revision"},
 "limits":["Selected-winner sample cannot measure false positives or predictive breadth.","No dated historical analyst estimate vintage, earnings-surprise consensus, or revision series reconstructed.","No primary transcript Q&A collected; management evidence consists of release statements and filing MD&A.","Only latest preselection 10-Q for each issuer independently tied to SEC index acceptance; earlier evidence is issuer release based.","No reclassified recurring earnings series imposed. Adjustment differences are retained.","STX next-quarter gross/operating margin is not guided numerically in the reviewed releases.","Yfinance/current ratios cannot establish contemporaneous expectations or institutional accumulation."],
 "inference":"Both issuers show recovery from depressed comparison periods, supply/cost discipline and cloud-related product mix improvements. Different physical drivers and mixed pricing mean this is a plausible common economic-family hypothesis, not a single commodity cycle or established cause of share appreciation."
}
ROOT.mkdir(parents=True,exist_ok=True)
with (ROOT/'quarter_timeline.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader();w.writerows(rows)
(ROOT/'source_evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n')
print(json.dumps({"rows":len(rows),"issuer_releases":len(evidence['sources']),"acceptance_verified_filings":len(filings),"last_MU":rows[9],"last_STX":rows[-1]},indent=2))
