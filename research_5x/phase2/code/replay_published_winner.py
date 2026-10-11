"""Portable independent winning-account replay; original ZIP audit remains separate."""
from phase2_bootstrap import e,ROOT,OUT
from audit_winning_account import independent_replay,read_csv,comparison
import json
import continuation_engine as adapter

def main():
    ref=ROOT/'research_5x/continuation/2026-10-11/fresh_hit'
    prices=e.load_gz(e.REPO/'backtests/staged/wf3_prices.json.gz');spy=json.loads((ROOT/'research_5x/data/spy.json').read_text())
    curve=read_csv(ref/'replay20_curve.csv');trades=read_csv(ref/'replay20_trades.csv');signals=read_csv(ref/'replay20_signals.csv')
    audit=independent_replay(prices,spy,curve,trades,signals)
    expected=json.loads((ref/'results.json').read_text())['diagnostics'][0]['result']
    comparison(expected['pnl_by_ticker'],audit['result']['pnl_by_ticker'],'IndependentissuerP&L')
    frames,panel,calendar=e.prepare(prices,e.load_gz(e.REPO/'backtests/staged/wf3_valuein_fundamentals.json.gz'),spy)
    cfg={**next(c for c in e.CONFIGS if c['name']=='growth_margin5'),'retain_rank35':True,'preserve_weights':True,'holding_rule':'retain_and_preserve','delay_sessions':0}
    result,*_=adapter.simulate(cfg,frames,panel,calendar,start='2025-06-02',end='2026-06-02',cost_bps=20)
    comparison(expected,e.clean(result),'Frozenfullresult')
    print(json.dumps({'pass':True,'independent_replay':audit['result'],'frozen_engine_all_fields_match':True,
                      'archive_audit':'See original audit/summary.json; thisportablecommand does not verify the omittedOctober11ZIP'},indent=2))
if __name__=='__main__':main()
