"""Expand exact missing-field audit with security/date price and certification gaps."""
import pandas as pd,json
from pathlib import Path
O=Path(__file__).resolve().parent
c=pd.read_csv(O/'pit_data_coverage.csv');c=c[c.status.isin(['MISSING_QUARTER_INPUT','MISSING_PERIOD_INPUT'])]
s=pd.read_csv(O/'stock_selection_audit.csv');rows=c.to_dict('records')
for r in s[~s.price_present].itertuples():
 status='PUBLIC_PRICE_RECOVERED_EA_SEPARATE_RECONSTRUCTION' if r.ticker=='EA' else 'AVB_PUBLIC_QUOTE_NONSTANDARD_ACTION_UNRESOLVED' if r.ticker=='AVB' else 'MISSING_HISTORICAL_PRICE_PUBLIC_PROBE_FAILED'
 rows.append({'ticker':r.ticker,'signal_date':r.signal_date,'field':'daily_ohlcv_dividends_splits','required_period':'126 prior sessions plus next-session execution','status':status,'source':'archive plus Yahoo public-price probe','price_present':False})
a=pd.read_csv(O/'signal_audit.csv.gz')
for r in a[a.fact_status!='VERIFIED_SAME_ACCESSION_QUARTER'].itertuples():rows.append({'ticker':r.ticker,'signal_date':r.signal_date,'field':r.concept,'required_period':r.period_end,'accession':r.accession,'status':r.fact_status,'source':r.sec_facts_url})
for ds in sorted(s.signal_date.unique()):
 for field,status in [('membership_announcements_effective_dates','PRIMARY_MEMBERSHIP_LINEAGE_UNCERTIFIED'),('industry_classification','HISTORICAL_INDUSTRY_MISSING'),('dividend_payable_dates','EX_DATE_CASH_APPROXIMATION'),('execution_quote_liquidity','DAILY_OPEN_FILL_MODEL_NOT_EXECUTION_CERTIFICATION')]:rows.append({'ticker':'UNIVERSE_OR_ACCOUNT','signal_date':ds,'field':field,'status':status})
pd.DataFrame(rows).to_csv(O/'pit_data_coverage.csv',index=False)
print('Coverage gaps',len(rows))
