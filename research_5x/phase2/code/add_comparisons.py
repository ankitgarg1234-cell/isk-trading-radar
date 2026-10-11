"""Add frozen SPY and continuous-policy comparisons without new simulations."""
from phase2_bootstrap import ROOT,OUT,e
import pandas as pd,json

def main():
    old=ROOT/'research_5x/continuation/2026-10-11/experiments'
    ref=json.loads((old/'results.json').read_text())['fresh_spy_accounts']
    bench=pd.DataFrame(ref)[['start','end','net_return_pct','max_dd_pct']].rename(columns={'net_return_pct':'spy_return_pct','max_dd_pct':'spy_dd_pct'})
    accounts=pd.read_csv(OUT/'retention/accounts.csv')
    accounts=accounts.drop(columns=['spy_return_pct','spy_dd_pct','excess_spy_pp'],errors='ignore').merge(bench,on=['start','end'],how='left')
    assert accounts.spy_return_pct.notna().all()
    accounts['excess_spy_pp']=accounts.return_pct-accounts.spy_return_pct
    accounts.to_csv(OUT/'retention/accounts.csv',index=False)
    bench.to_csv(OUT/'retention/spy_accounts.csv',index=False)
    full=pd.read_csv(old/'continuous_summary.csv');full.to_csv(OUT/'retention/prior_continuous_summary.csv',index=False)
    cols=['candidate','scenario','net_return_pct','max_dd_pct','rolling12_max_pct','rolling12_median_pct','worst_complete_calendar_year_pct','annual_oneway_turnover_over_avg_equity']
    subset=full[((full.phase=='baseline')|((full.candidate=='growth_margin5')&(full.scenario=='retain_and_preserve_20bps')))]
    subset.to_csv(OUT/'retention/continuous_comparison.csv',index=False)
    # Corresponding returns use marked holdings and same source conventions.
    extra='<h3>Earlier continuous-account comparison</h3><div class="scroll">'+subset[cols].to_html(index=False,border=0,float_format=lambda v:f'{v:,.2f}')+'</div><p>These continuously funded accounts span January 2024–October 2026. Their total return is not a one-year return. The retained rotational growth/margin policy reaches +359.56% in its best strict annual window, a 40.44 percentage-point gap to +400%, with −34.20% full-period drawdown. It remains a provisional research alternative, with the same source and reused-history limits. The deployed frozen portfolio ledger is unavailable, so its prior headline metrics cannot be independently compared.</p><p><a href="retention/continuous_comparison.csv">Frozen full-period comparisons</a> · <a href="retention/spy_accounts.csv">Same-date cash-funded SPY accounts</a></p>'
    report=OUT/'research_report.html';s=report.read_text();s=s.replace('<h2 id="history">',extra+'<h2 id="history">');report.write_text(s)
if __name__=='__main__':main()
