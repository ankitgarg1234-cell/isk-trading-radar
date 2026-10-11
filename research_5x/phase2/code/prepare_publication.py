"""Research-only publication inventory, dependency snapshots and new archive."""
from phase2_bootstrap import ROOT,OUT,e
from pathlib import Path
import hashlib,json,zipfile,os
import pandas as pd

def main():
    r=OUT/'retention';f=pd.read_csv(r/'accounts.csv');orders=[];lineage=[]
    old=ROOT/'research_5x/continuation/2026-10-11/experiments'
    for start in sorted(f.start.unique()):
        p=old/'fresh_accounts'/('growth_margin5__rebalance__'+start+'_trades.csv')
        a=pd.read_csv(p);a=a[a.date.eq(a.date.min())&a.side.eq('BUY')].copy();a['start']=start;orders.append(a)
        lineage.append({'start':start,'source_path':str(p.relative_to(ROOT)),'source_sha256':e.sha(p)})
    pd.concat(orders,ignore_index=True).to_csv(r/'frozen_initial_orders.csv',index=False)
    e.dump(r/'frozen_initial_orders_lineage.json',lineage)
    history=OUT/'history';histfiles=[f for f in history.rglob('*') if f.is_file() and 'local_cache' not in f.parts and f.suffix in ['.csv','.json']]
    histzip=history/'earlier_prices.zip'
    with zipfile.ZipFile(histzip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in sorted(histfiles):z.write(f,str(f.relative_to(history)))
    phasefiles=[f for f in OUT.rglob('*') if f.is_file() and 'local_cache' not in f.parts and '__pycache__' not in f.parts and f.name not in ['publication_manifest.json','publication_receipt.json','local_package_receipt.json']]
    codefiles=[f for f in (ROOT/'research_5x/phase2/code').glob('*') if f.is_file()]
    dependencies=[ROOT/'research_5x/code'/x for x in ['run_research.py','continuation_engine.py']]
    dependencies += [ROOT/'research_5x/data/spy.json',ROOT/'research_5x/results/monthly_features_labels.csv.gz',old/'results.json',old/'continuous_summary.csv']
    hit=ROOT/'research_5x/continuation/2026-10-11/fresh_hit'
    dependencies += [hit/x for x in ['replay20_curve.csv','replay20_trades.csv','replay20_signals.csv','results.json']]
    excluded=['Recreatable annotated fullpanel (3.65MB), sourcefrozenmonthlypanel is included','EarlierpriceCSVoriginals are inside history/earlier_prices.zip','VisualQA screenshots are localarchiveonly; checks.jsonpublished','Vendor dependencies, cookiecache and bytecode excluded']
    public=[]
    for f in phasefiles:
        rel=str(f.relative_to(OUT))
        if rel=='panel/annotated_panel.csv.gz':continue
        if rel.startswith('history/') and f!=histzip:continue
        if rel.startswith('visual_qa/') and f.suffix!='.json':continue
        public.append(f)
    public+=codefiles+dependencies
    def record(f):return {'path':str(f.relative_to(ROOT)),'bytes':f.stat().st_size,'sha256':e.sha(f),'encoding':'base64'}
    manifest={'branch':'research/phase2-earnings-acceleration','parent_sha':'964189d6228e273b2a9154c49e3a70e3fb45872c',
      'base_tree_sha':'2b57d699116b986a189254ebb70fbc56660bb9d3','files':[record(f) for f in sorted(set(public))],
      'exclusions':excluded,'repository_inputs_already_in_base':['backtests/staged/wf3_prices.json.gz','backtests/staged/wf3_valuein_fundamentals.json.gz','scripts/wf3_offline_valuein.py'],
      'original_archive_sha256':'1315b523195777aea09edb40cf2c1534d81652886d7110f9dcb0c02ca3ab0af8'}
    e.dump(OUT/'publication_manifest.json',manifest)
    # Local full milestone, no duplicate11.5MBpricecache and no networkprivatecache.
    archive=ROOT/'sp500_5x_phase2_2026-10-11.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in sorted(set(phasefiles+codefiles+dependencies+[OUT/'publication_manifest.json'])):
            if f==histzip:continue # originalCSVsnapshots already included in localfullrecord
            z.write(f,str(f.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    receipt={'path':archive.name,'bytes':archive.stat().st_size,'sha256':e.sha(archive),'crc_pass':True,'publication_files':len(public),'publication_bytes':sum(f.stat().st_size for f in public),
             'archive_layout':'Researchsources/results; frozenpricefundamentalinputs remain in originalresearchbranchbase orOctober11archive; oldarchiveunchanged.'}
    e.dump(OUT/'local_package_receipt.json',receipt);print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
