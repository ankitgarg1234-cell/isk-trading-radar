"""Exact GEM archived-input reproduction only; no production imports."""
import sys, json, pickle, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_5x/code'))
import run_research as base
base.REPO=ROOT
import continuation_engine as adapter

def main():
    OUT.mkdir(exist_ok=True)
    prices=base.load_gz(ROOT/'backtests/staged/wf3_prices.json.gz')
    funds=base.load_gz(ROOT/'backtests/staged/wf3_valuein_fundamentals.json.gz')
    spy=json.loads((ROOT/'research_5x/data/spy.json').read_text())
    frames,panel,calendar=base.prepare(prices,funds,spy)
    with (OUT/'archive_prepared.pkl').open('wb') as f:pickle.dump((frames,panel,calendar),f)
    cfg=next(c for c in base.CONFIGS if c['name']=='growth_margin5')
    result,curve,trades,rolling,signals=base.simulate(cfg,frames,panel,calendar)
    archived=json.loads((ROOT/'research_5x/continuation/2026-10-11/experiments/results.json').read_text())
    expected=next(s['result'] for s in archived['continuous_scenarios'] if s['spec']['candidate']=='growth_margin5' and s['spec']['scenario']=='baseline')
    keys=['net_return_pct','max_dd_pct','rolling12_max_pct','rolling12_median_pct','total_cost_dollars','trade_count']
    checks={k:{'expected':expected[k],'reproduced':base.clean(result[k]),'difference':float(result[k])-float(expected[k])} for k in keys}
    assert all(abs(r['difference'])<1e-7 for r in checks.values()),checks
    base.dump(OUT/'archive_reproduction.json',{'status':'PASS_ACCOUNTING_CONFIGURATION_ONLY','checks':checks,'source_sha256':base.sha(Path(base.__file__)),'original_configuration':cfg,'original_start':base.START,'original_end':base.END,'original_inputs':[{'path':p,'sha256':base.sha(ROOT/p)} for p in ['backtests/staged/wf3_prices.json.gz','backtests/staged/wf3_valuein_fundamentals.json.gz','research_5x/data/spy.json']],'pit_certified':False,'versions':{'pandas':base.pd.__version__,'numpy':base.np.__version__}})
    curve.to_csv(OUT/'archived_full_curve.csv',index=False)
    panel.drop(columns=['forward_252d','label_end','path_dd','path_min_return','residual'],errors='ignore').to_csv(OUT/'archived_signal_features.csv.gz',index=False)
    print(json.dumps(checks),flush=True)

if __name__=='__main__':main()
