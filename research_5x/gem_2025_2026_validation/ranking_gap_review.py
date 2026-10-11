"""Distinguish provable gate failures from unresolved rank competition."""
from pathlib import Path
import pandas as pd
O=Path(__file__).resolve().parent
s=pd.read_csv(O/'stock_selection_audit.csv');a=pd.read_csv(O/'signal_audit.csv.gz');records=[]
by={k:g for k,g in a.groupby(['signal_date','ticker'])}
for x in s.itertuples():
 g=by.get((x.signal_date,x.ticker));proved=[]
 def verified(fields):
  if g is None:return False
  for field in fields:
   p=g[g.concept==field]
   if len(p)<2 or not (p.fact_status=='VERIFIED_SAME_ACCESSION_QUARTER').all():return False
  return True
 if pd.notna(x.revenue_yoy) and x.revenue_yoy<=.2 and verified(['TotalRevenue']):proved.append('verified_revenue_growth_failure')
 if pd.notna(x.margin_delta_pp) and x.margin_delta_pp<=3 and verified(['TotalRevenue','OperatingIncome']):proved.append('verified_margin_failure')
 # Known nonpositive price momentum excludes independently, although archive bar lineage remains uncertified.
 if pd.notna(x.r63) and x.r63<=0:proved.append('archived_nonpositive_momentum')
 unresolved=g is None or not (g.fact_status=='VERIFIED_SAME_ACCESSION_QUARTER').all()
 gaps=unresolved or not x.price_present or pd.isna(x.revenue_yoy) or pd.isna(x.margin_delta_pp)
 records.append({'signal_date':x.signal_date,'ticker':x.ticker,'archived_rank':x.rank,'observed_data_gap':gaps,'proved_failure_on_observed_data':'|'.join(proved),'requires_further_rank_competition_review':bool(gaps and not proved),'status':'TRIAGE_NOT_COMPLETE_ELIGIBILITY_CERTIFICATION'})
out=pd.DataFrame(records);out.to_csv(O/'ranking_gap_review.csv',index=False)
out[out.requires_further_rank_competition_review].to_csv(O/'potentially_displacing_competitors.csv',index=False)
print('Unresolved competitors requiring review',int(out.requires_further_rank_competition_review.sum()),'of',len(out),'security/date rows')
