"""Build the research record without fitting a strategy to uncertified data."""
from pathlib import Path
import base64,html,json,re
import pandas as pd
import numpy as np
OUT=Path(__file__).resolve().parents[1]
A=OUT/'accounting_quality'

def build_tables():
    a=pd.read_csv(A/'mature_cohorts.csv');cov=pd.read_csv(A/'company_coverage.csv')
    peers=pd.read_csv(A/'issuer_audits/matched_peers/signal_case_matrix.csv')
    fails=pd.read_csv(A/'issuer_audits/failures/case_metrics.csv')
    reviewed=set(peers.ticker)|set(fails.ticker)|{'MU','STX','WDC'}
    company=a.groupby('ticker').agg(mature_observations=('date','size'),first_signal=('date','min'),last_mature_signal=('date','max'),mean_forward_price_return_pct=('forward_252d',lambda x:x.mean()*100),median_forward_price_return_pct=('forward_252d',lambda x:x.median()*100),negative_labels=('forward_252d',lambda x:int((x<0).sum())),material_labels=('forward_252d',lambda x:int((x<-.10).sum())),severe_labels=('forward_252d',lambda x:int((x<=-.30).sum()))).reset_index().merge(cov,on='ticker')
    company['original_case_packet']=company.ticker.isin(reviewed)
    company['whole_company_monthly_certification']='not_completed'
    company['coverage_note']=company.ticker.map({'WDC':'HDD income/Flash cash; original/revised Q4 scope/vintage bridge','MU':'Patent/inventory-cost profit and gross/adjusted FCF bridge','STX':'Divestiture gain versus operating cash classification','APP':'Continuing income versus consolidated cash; Apps scope bridge','NVDA':'Combined PPE/intangibles; pure gross-PPE FCF missing','DECK':'October release precedes matching cash filing','LVS':'Standard cash tag requires repair'}).fillna('Targeted original case evidence; full monthly scope/vintage audit incomplete')
    company.loc[~company.original_case_packet,'coverage_note']='API staging only; original company accounting-quality audit missing'
    company.to_csv(A/'company_accounting_comparison.csv',index=False)
    all_rows=pd.read_csv(A/'all_qualified_with_labels.csv')
    universe=all_rows.groupby('ticker').agg(qualified_rows=('date','size'),mature_rows=('forward_252d','count'),first_signal=('date','min'),last_signal=('date','max')).reset_index()
    universe['original_case_packet']=universe.ticker.isin(reviewed)
    universe['source_status']=np.where(universe.mature_rows>0,'mature cohort API staging; full original certification incomplete','censored-only issuer retained; accounting expansion not yet attempted')
    universe.to_csv(A/'all_66_company_coverage.csv',index=False)
    failure=a[a.forward_252d<0].copy();failure['source_review_exact_signal']=False;failure['observable_entry_accounting_concern']='not_established_for_this_signal';failure['causal_failure_attribution']='unproven';failure['later_information_used_as_predictor']=False
    for _,x in fails.iterrows():
        mask=(failure.ticker==x.ticker)&(failure.date==x.signal_date)
        failure.loc[mask,'source_review_exact_signal']=True
        failure.loc[mask,'observable_entry_accounting_concern']=x.notes
    for _,x in peers.iterrows():
        mask=(failure.ticker==x.ticker)&(failure.date==x.signal_date)
        failure.loc[mask,'source_review_exact_signal']=True
        failure.loc[mask,'observable_entry_accounting_concern']='See original peer accounting packet; clean cash/profit is not a sufficient stock-return condition.'
    # The mandatory early-MU packet applies to the released Q2 setup only.
    mask=(failure.ticker=='MU')&(failure.date.isin(['2024-03-28','2024-04-30','2024-05-31']))
    failure.loc[mask,'source_review_exact_signal']=True
    failure.loc[mask,'observable_entry_accounting_concern']='FY24Q2 patent gain and previously written-down inventory lower-cost benefit; gross-PPE FCF negative. Causal loss attribution unproven.'
    failure.to_csv(A/'failure_attribution.csv',index=False)
    sources=[{'path':'retention/prior_phase2/'+p.name,'evidence':'immutable Phase2 dependent portfolio accounts; no Phase3 policy evaluation'} for p in sorted((OUT/'retention/prior_phase2').iterdir())]
    pd.DataFrame(sources).to_csv(OUT/'retention/prior_evidence_references.csv',index=False)
    return a,company,fails

def plots(a,fails):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#263d49','text.color':'#263d49','axes.titleweight':'bold'})
    d=OUT/'figures';d.mkdir(exist_ok=True)
    cats=['exceptional','moderate','flat_modest','material_loser','severe_loser'];labels=['≥100%','30–<100%','−10–<30%','−30–<−10%','≤−30%']
    fig,ax=plt.subplots(figsize=(9.5,4.1));x=np.arange(5);first=a[a.first_observed_company_signal]
    for shift,s,color,name in [(-.19,a,'#257b83','All188 observations'),(.19,first,'#d6aa62','First39 company signals')]:
        n=s.outcome.value_counts().reindex(cats,fill_value=0);bars=ax.bar(x+shift,n/len(s)*100,.35,color=color,label=name)
        for b,count in zip(bars,n):ax.text(b.get_x()+b.get_width()/2,b.get_height()+.8,str(count),ha='center',fontsize=10)
    ax.set_xticks(x,labels);ax.set_ylabel('Share of this historical sample (%)');ax.set_ylim(0,40);ax.legend(frameon=False);ax.set_title('Outcome repetition changes the apparent distribution',loc='left');fig.tight_layout();fig.savefig(d/'cohort_outcomes.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9.5,4.1));counts=[71/188*100,76/188*100,10/39*100,9/39*100];labs=['Strict · all','Relaxed · all','Strict · first only','Relaxed · first only']
    bars=ax.barh(labs,counts,color=['#257b83','#257b83','#d6aa62','#d6aa62']);ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('Observations with a nearest peer (%)');ax.set_title('Comparable cases are scarce after repeat signals are removed',loc='left')
    for b,v,t in zip(bars,counts,['71/188','76/188','10/39','9/39']):ax.text(v+1,b.get_y()+b.get_height()/2,t,va='center')
    fig.tight_layout();fig.savefig(d/'match_coverage.png',dpi=170);plt.close(fig)
    # Fixed failure cases, not a representative factor sample.
    s=fails[fails.ticker.isin(['DXCM','DECK','FSLR','TTD','DASH']) & fails.analyst_fcf.notna()].copy();s['fcf_margin']=s.analyst_fcf/s.revenue*100
    fig,ax=plt.subplots(figsize=(9.5,4.1));bars=ax.bar(s.ticker,s.fcf_margin,color=['#257b83' if v>=0 else '#b66055' for v in s.fcf_margin]);ax.axhline(0,color='#809198',lw=.8);ax.set_ylabel('CFO minus gross PPE / revenue (%)');ax.set_title('Positive free cash flow did not prevent severe stock losses',loc='left')
    for b,(_,r) in zip(bars,s.iterrows()):ax.annotate(f'{r.forward_252d*100:.1f}% stock return',xy=(b.get_x()+b.get_width()/2,b.get_height()),xytext=(0,6 if b.get_height()>=0 else -14),textcoords='offset points',ha='center',fontsize=9)
    ax.set_ylim(min(-26,s.fcf_margin.min()-10),max(50,s.fcf_margin.max()+10));fig.tight_layout();fig.savefig(d/'cash_failure_cases.png',dpi=170);plt.close(fig)
    prior=pd.read_csv(OUT/'retention/prior_phase2/summary.csv').query('bps == 20');fig,ax=plt.subplots(figsize=(9.5,4.3));labels={'monthly_equal':'Monthly equal','quarterly_equal':'Quarterly equal','untouched_hold':'Untouched','monthly_cap25_only':'Monthly25% cap','fundamental_exit_only':'Fundamental exit','relative_strength_exit_only':'Relative-strength exit'}
    for _,r in prior.iterrows():
        ax.scatter(-r.largest_account_dd_pct,r.median_return_pct,s=80,color='#257b83');ax.annotate(labels[r.policy],(-r.largest_account_dd_pct,r.median_return_pct),xytext=(4,5),textcoords='offset points',fontsize=9)
    ax.set_xlim(27,38);ax.set_ylim(16,37);ax.set_xlabel('Worst account drawdown magnitude (%)');ax.set_ylabel('Median12-month net return (%)');ax.set_title('Prior Phase2 holding tradeoffs ·22 overlapping starts',loc='left');fig.tight_layout();fig.savefig(d/'prior_retention_tradeoff.png',dpi=170);plt.close(fig)

def table(df):
    display=df.rename(columns=lambda c:str(c).replace('_',' '))
    return '<div class="scroll">'+display.to_html(index=False,border=0,escape=True,float_format=lambda x:f'{x:,.2f}',na_rep='Missing')+'</div>'

def readable_text(body):
    """Space numeric prose without changing links, CSS or embedded image data."""
    def fix(match):
        s=match.group()
        s=re.sub(r'(?<=[A-Za-z])(?=\d)', ' ', s)
        s=re.sub(r'(?<=\d)(?=[A-Za-z])', ' ', s)
        s=re.sub(r'(?<=[A-Za-z])(?=[$+−])', ' ', s)
        s=s.replace(' /',' / ').replace('the91','the 91')
        # Quarter identifiers and ordinary monetary units remain compact.
        s=re.sub(r'\bQ ([1-7])\b', r'Q\1', s)
        s=re.sub(r'(\d) m\b', r'\1m', s)
        s=re.sub(r'(\d) pp\b', r'\1pp', s)
        s=re.sub(r'\bFY (\d{4}) Q', r'FY\1 Q', s)
        s=s.replace('4 ea 4401','4ea4401').replace('research/phase 3-accounting','research/phase3-accounting')
        return s
    return re.sub(r'(?<=>)[^<]+(?=<)',fix,body)
def picture(name,caption):
    data=base64.b64encode((OUT/'figures'/name).read_bytes()).decode()
    return '<figure><img alt="'+html.escape(caption)+'" src="data:image/png;base64,'+data+'"><figcaption>'+html.escape(caption)+'</figcaption></figure>'
def link(path,label):return f'<a href="{html.escape(path)}">{html.escape(label)}</a>'

def report(a,company,fails):
    status=json.load(open(OUT/'VALIDATION_STATUS.json'));summ=pd.read_csv(A/'cohort_summary.csv');unc=pd.read_csv(A/'descriptive_uncertainty.csv');match=pd.read_csv(A/'match_summary.csv');prior=pd.read_csv(OUT/'retention/prior_phase2/summary.csv').query('bps==20');gate=status['gates']
    q=pd.DataFrame([{'Question':k,'Classification':v['classification'],'Conclusion':v['answer']} for k,v in status['conclusions'].items()])
    facts=fails[['ticker','signal_date','revenue','operating_income','net_income','cfo','gross_capex','analyst_fcf','sbc','forward_252d']].copy();facts['forward_252d']*=100;facts.rename(columns={'forward_252d':'252-session price return %'},inplace=True)
    body=f'''<header><p class="eyebrow">S&amp;P500 rotational research · Phase3 ·11 October2026</p><h1>Accounting quality matters.<br>It does not explain the winners on its own.</h1><p class="lead">Original financial evidence exposes temporary profit, cash-definition differences and reporting-scope breaks. Several severe stock failures still had positive operating profit and free cash flow. Broad predictive separation remains blocked by incomplete source certification and sparse comparable cases.</p><div class="cards"><div><strong>188 /39</strong><span>Mature stock observations / issuers<br>All379 qualified rows preserved</span></div><div><strong>16 issuers</strong><span>Targeted original-source audit packets<br>Partial monthly coverage</span></div><div><strong>10 /39</strong><span>Strict first-company matches<br>Current sector/size proxies</span></div><div><strong>Gate1 blocked</strong><span>No new timing or holding optimization<br>No account or production changes</span></div></div></header>
    <nav><a href="#finding">Accounting findings</a><a href="#cohort">Matched cohorts</a><a href="#coverage">Coverage and gates</a><a href="#prior">Prior portfolios</a><a href="#decision">Seven answers</a><a href="#record">Research record</a></nav>
    <section id="finding"><h2>What the original statements establish</h2><p><b>Micron’s early recovery was less clean than its headline profit suggested.</b> FY2024Q2 reported OI$191m included a$200m patent gain and$382m of lower costs from previously written-down inventory. Excluding only those two effects gives diagnostic OI−$391m; CFO less gross PPE was−$165m. In June2025 gross-PPE FCF was+$1,671m. These are source-backed financial distinctions, with incomplete recurring-profit normalization; they are not an independently validated return predictor. {link('accounting_quality/issuer_audits/memory/MU.md','MU original-vintage audit')}.</p>
    <p><b>Cash can be supported by a transaction or a different definition.</b> STX Q4FY2024 CFO$434m included$226m divestiture operating receipts; removing only those receipts gives CFO$208m and FCF$154m. The$313m disposal earnings gain was below OI, so subtracting it from OI would be wrong. WDC’s June2025 income describes continuing HDD but its cash still includes Flash; standalone cash conversion stays missing. WDC’s original Q4OI$507m/NI$330m and later annual-derived OI$216m/NI$39m remain distinct publication vintages. {link('accounting_quality/issuer_audits/memory/STX.md','STX classification bridge')}, {link('accounting_quality/issuer_audits/memory/WDC.md','WDC scope/vintage bridge')}.</p>
    <div class="callout"><b>Rejected: positive cash conversion is sufficient to prevent material stock losses.</b> DXCM, DECK September2024, TTD and DASH all had comparable positive CFO and gross-PPE FCF before subsequently losing more than30% in the frozen stock labels. This rejects a sufficient-condition claim; it does not reject incremental cash-quality information after proper controls.</div>
    {picture('cash_failure_cases.png','Fixed failure cases selected for forensic review; price-only stock labels, not portfolio outcomes or an unbiased factor sample.')}
    <h3>Failure issuer accounting comparison</h3><p>Income/cash amounts are USD millions. APP income is continuing while cash is consolidated; its row deliberately offers no continuing cash-conversion ratio. DECK’s October31 cash data are missing because the matching filing arrived after the October30 cutoff. DASH company FCF also deducts software capitalization; the common analyst definition here deducts gross PPE only.</p>{table(facts)}
    <p>{link('accounting_quality/issuer_audits/failures/ISSUER_AUDITS.md','All failure issuer audits and primary links')} · {link('accounting_quality/issuer_audits/failures/annual_Q4_reconciliation.csv','Original Q4/annual reconciliations')} · {link('accounting_quality/issuer_audits/matched_peers/FINDINGS.md','Matched peer source findings')} · {link('accounting_quality/issuer_audits/matched_peers/normalized_metrics.csv','Peer accounting metrics')}.</p>
    <p>Important retained differences: PLTR/NOW SBC addbacks and cash payroll/deferred-revenue effects, FSLR government-credit collection and expansion capex, NVDA combined PPE/intangibles, APP discontinued Apps, CCL export credits and the original-release/annual cash difference. Consolidated CFO requires consolidated earnings, not parent NI merely bearing a similar taxonomy name. No missing adjusted OI is replaced with adjusted EBITDA.</p></section>
    <section id="cohort"><h2>Matching limits the strength of any explanation</h2><p>The same fixed Phase2 gates produce39 exceptional,54 moderate,60 flat/modest,22 material-loser and13 severe-loser observations. Material losses below−10% include both loser groups;58 observations have any negative return. Labels never select accounting facts or nearest peers. Severe observations represent8 issuers, not13 independent companies.</p>{picture('cohort_outcomes.png','Numbers above bars are observation counts. Forward252-session close-price labels exclude dividends/costs and are dependent.')}
    <p>Strict matching fixes month, current-sector proxy and size quartile with63-session momentum gap≤20pp. Relaxed matching fixes month/sector, caps size ratio at2× and momentum gap at30pp. Strict quartiles can pair firms more than30× apart in capitalization; they do not certify comparable size. Both specifications retain unmatched rows.</p>{table(match[['specification','matched_observations','unmatched_observations','matched_issuers','cross_outcome_nearest_rows','median_momentum_gap','median_size_gap_log2']])}{picture('match_coverage.png','First-company sensitivity reruns matching with both companies restricted to first signals. Directed pairs may reuse peers.')}
    <p>All-observation median stock return is29.68%; first-company median is25.08%. Removing repeated signals lowers the mean from87.17% to51.35%. First observed is not first economic inflection: left-edge censoring remains. The two-year industry/date exposure cannot be removed by a small matching table.</p><h3>Descriptive statistical uncertainty</h3>{table(unc)}<p>Intervals are2.5/97.5 percentiles from2,000 draws, seed73011. Whole-issuer resampling preserves issuer repetition;12-month cohort blocks preserve some time dependence. Neither supplies independent market cycles or future5× probabilities. The first-company median interval even includes a slightly negative value. No quality/return regression, optimized cutoff or causal estimate is produced before Gate1 passes.</p>
    <details><summary>Company-by-company coverage for every mature issuer</summary>{table(company[['ticker','mature_observations','negative_labels','severe_labels','original_case_packet','cfo_present','capex_present','coverage_note']])}</details><p>{link('accounting_quality/company_accounting_comparison.csv','Complete company comparison')} · {link('accounting_quality/failure_attribution.csv','All58 negative cases and attribution status')} · {link('accounting_quality/strict_unmatched.csv','Strict unmatched cases')} · {link('accounting_quality/relaxed_unmatched.csv','Relaxed unmatched cases')}.</p></section>
    <section id="coverage"><h2>Data presence is not original-source certification</h2><p>All39 issuers have SEC Company Facts/Submissions snapshots;188 signal observations select91 filings. CFO/NI/revenue/SBC appear for185/188 observations, gross PPE for163/188. These are staging values, with source-accession lineage and no predictive-use permission. WDC/APP mismatched cash ratios are blank, parent-NI ambiguity is explicit, and original release timing can differ from the latest full filing.</p><p>58 of the91 selected accessions have a four/five-hour disagreement between current API acceptance strings and the frozen cache. Original indices independently confirm specific conflicts; the bulk inventory does not silently choose an authority. Full original release/index/scope certification is incomplete across the cohort. Historical sector/industry and size remain proxies. {link('DATA_COVERAGE.md','Exact coverage, source cost and unblock requirements')} · {link('accounting_quality/timestamp_conflicts.csv','All timestamp conflicts')} · {link('accounting_quality/missingness_coverage.csv','Missingness by outcome, sector and date')}.</p>
    {table(pd.DataFrame([{'Gate':k,'Status':v['status'],'Reason':v['blocker']} for k,v in gate.items()]))}
    <p>SEC/IR public evidence involved no data purchase. Some original SEC/IR binary downloads returned403, while other originals and web reviews succeeded; all attempts are recorded. Credit exhaustion interrupted collection and work resumed. Yahoo remains the selected price source. Selected surviving2010–2023 price histories are not a point-in-time S&amp;P500 universe. No complete historical membership/terminal-proceeds/consensus export was obtained. {link('validation/PROSPECTIVE_PROTOCOL.md','Prospective independent research protocol')} is a document only; no paper account or scheduler was started.</p></section>
    <section id="prior"><h2>Preserved portfolio evidence · no new Phase3 policy result</h2><p>These are the frozen Phase2 accounts, not new entry, hybrid or rotation tests. All initial baskets/quantities are identical across each six-policy comparison and no replacement stocks enter. All22 annual starts overlap within reused history; percentages are dependent observations.</p>{picture('prior_retention_tradeoff.png','Prior20bps-per-side fixed-basket accounts. Untouched holding improves median return but increases worst drawdown and concentration.')}{table(prior[['policy','median_return_pct','mean_return_pct','worst_return_pct','largest_account_dd_pct','fivefold_accounts','max_company_weight_pct','max_cluster_weight_pct']])}
    <p>The same June2025 basket returned+392.75% monthly equal-weighted and+463.52% untouched, with−18.20%/−18.89% drawdown. Same-period SPY returned+28.48% with−8.37% drawdown. The separate independently reconciled rotational winner returned+410.82% with−18.00% drawdown. These are different policies, not addable stock returns. Storage/memory generated87.6% of that account’s net profit; the prior exclusion experiment reduced its return to about+104.14%. The two untouched5× starts are June/July2025 in one overlapping industry interval.</p>
    <p>The prior continuing retained rotational account’s best annual window was+359.56%, with full-period drawdown−34.20%; its total+522.30% spans2024–2026. Its structure admits replacement stocks and is not the frozen-basket experiment. No validated best annual return/drawdown frontier exists. Full prior daily NAVs and orders are preserved in {link('retention/prior_phase2/curves.csv.gz','daily NAVs')} and {link('retention/prior_phase2/trades.csv.gz','orders')}; {link('retention/STATUS.md','conditional holding work')} remains gate-blocked.</p></section>
    <section id="decision"><h2>Seven explicit research answers</h2>{table(q)}<p>No investment-rule conclusion is classified Validated. Independent source/arithmetic checks establish that records and accounting bridges reconcile; they do not create independently tested strategy performance.</p></section>
    <section id="record"><h2>Reproducible record and next experiment</h2><p>The next task is source completion, not another return threshold: reconcile original release/index and consolidated cash/earnings scope across the full qualified cohort, repair historical industry/size controls, then test frozen cash/adjustment measures without losing unsuccessful cases. Only a credible incremental signal can advance to entry/holding experiments and independent validation.</p><p>{link('PROTOCOL.md','Frozen protocol')} · {link('DECISION_LOG.md','Accepted, rejected and unproven hypotheses')} · {link('EXPERIMENT_QUEUE.csv','Ranked experiment queue')} · {link('VALIDATION_STATUS.json','Machine-readable gates')} · {link('README.md','Reproduction instructions')} · {link('validation/verification.json','Automated verification')}.</p><p>Parent4ea4401 · research/phase3-accounting-quality-validation. No deployed dashboard, production code, paper account, live position, broker connection or deployment configuration changed. No trades, leverage or production merge.</p></section>'''
    css='''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f5f5f1;color:#253d49;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:auto;padding:46px 36px}header{padding:30px 0}h1{font-size:44px;line-height:1.15;letter-spacing:-1.2px;margin:18px 0 24px}h2{font-size:29px;line-height:1.25;margin:0 0 18px}h3{font-size:21px}p{max-width:1050px}.lead{font-size:20px;max-width:1000px}.eyebrow{font-size:13px;text-transform:uppercase;letter-spacing:1.2px;color:#52717c}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:30px 0}.cards div{background:#e7efed;border-top:3px solid #287b83;padding:17px}.cards strong{display:block;font-size:25px}.cards span{font-size:13px;display:block;margin-top:8px}nav{display:flex;flex-wrap:wrap;gap:18px;border-top:1px solid #ccd6d6;border-bottom:1px solid #ccd6d6;padding:15px 0;font-size:13px}a{color:#1e6877;text-decoration-thickness:1px;text-underline-offset:3px}section{background:white;padding:28px;margin:28px 0;border:1px solid #e0e5e5}.callout{padding:18px 22px;background:#fcf3df;border-left:4px solid #bc9550}.scroll{overflow-x:auto;margin:18px 0}table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.4}th{text-align:left;background:#eaf0ef;color:#26464d;font-weight:600}th,td{padding:10px 9px;border-bottom:1px solid #dce4e4;vertical-align:top}figure{margin:24px 0}img{display:block;max-width:100%;height:auto}figcaption{font-size:12px;color:#5f7179;line-height:1.5;margin-top:8px}details{margin:18px 0}summary{cursor:pointer;font-weight:600}@media(max-width:650px){main{padding:18px 13px}h1{font-size:32px}h2{font-size:25px}.lead{font-size:17px}.cards{grid-template-columns:repeat(2,1fr);gap:9px}.cards strong{font-size:21px}section{padding:18px 13px}nav{gap:10px}table{min-width:680px}}'''
    (OUT/'research_report.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 3 — Accounting quality and validation</title><style>'+css+'</style></head><body><main>'+readable_text(body)+'</main></body></html>')

def main():
    a,c,f=build_tables();plots(a,f);report(a,c,f)
    print('Built company comparison, all-negative attribution and executive HTML. No quality factor fit or new portfolio backtest.')
if __name__=='__main__':main()
