"""Bounded, explicit public demo recovery. No account token or trading access.

Raw responses and source manifests always stay in ignored research storage.
HTTP errors are recorded without URLs that could contain secrets.
"""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from research.eodhd_client import NoRedirect, ResearchClient, usage_summary
from research.eodhd_probe import validate_prices
from research.spgm_sources import DEFAULT_OUTPUT

OUT = DEFAULT_OUTPUT/'historical_backtest/recovery_316'
DEMO_SYMBOLS = {'AAPL.US','AMZN.US','TSLA.US','EURUSD.FOREX'}
# Only AAPL actions are explicitly documented by the action demo footnote.
DEMO_COSTS = {'eod':1,'div':1,'splits':1,'fundamentals':10}


def recover_demo(endpoint,symbol):
    if symbol not in DEMO_SYMBOLS or endpoint not in DEMO_COSTS:
        raise ValueError('Not an approved documented public demo request')
    if endpoint in {'div','splits'} and symbol!='AAPL.US':
        raise ValueError('Only AAPL action demo explicitly approved')
    folder=OUT/'demo';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(symbol.replace('.','_')+'_'+endpoint+'.json')
    if path.exists():return path
    ledger=OUT/'demo_request_manifest.json'
    state=json.loads(ledger.read_text()) if ledger.exists() else []
    if len(state)>=9:raise RuntimeError('Public demo experiment request cap reached')
    params={'api_token':'demo','fmt':'json'}
    if endpoint!='fundamentals':params.update({'from':'2021-01-01','to':'2026-09-30'})
    else:params['filter']='General'
    entry=dict(endpoint=endpoint,symbol=symbol,credential='PUBLIC_DOCUMENTED_DEMO',
        configured_account_units=0,nominal_endpoint_cost=DEMO_COSTS[endpoint],
        at=datetime.now(timezone.utc).isoformat(),source_url='https://eodhd.com/api/'+endpoint+'/'+symbol)
    state.append(entry);ledger.write_text(json.dumps(state,indent=2)+'\n')
    try:
        request=Request(entry['source_url']+'?'+urlencode(params),headers={'User-Agent':'SPGM-personal-research/1.0'})
        with build_opener(NoRedirect()).open(request,timeout=30) as response:
            body=response.read();payload=json.loads(body)
        path.write_bytes(body)
        entry.update(status=200,sha256=hashlib.sha256(body).hexdigest(),path=str(path),
                     records=len(payload) if isinstance(payload,list) else None)
    except HTTPError as exc:entry.update(status=exc.code)
    except (URLError,TimeoutError,OSError,ValueError):entry.update(status='connection_or_payload_failure')
    ledger.write_text(json.dumps(state,indent=2)+'\n')
    return path if path.exists() else None


def account_pilot():
    """Explicit three-unit experiment; cached final evidence prevents repeats."""
    required=['SPY_US_eod.json','US_active_symbols.json','US_delisted_symbols.json','account_final.json']
    if all((OUT/n).exists() for n in required):
        return {'status':'CACHED','new_account_requests':0}
    client=ResearchClient(OUT/'eodhd_request_ledger.json',budget=3,request_limit=6)
    account=client.get('user')
    quota=usage_summary(account)
    # Before a reset, budget against last reported remaining, not unobserved
    # extra credits. This deliberately permits at most three charged units.
    if quota['reported_remaining_units']<3:
        raise RuntimeError('Conservative account allowance below three units')
    if account.get('subscriptionType')!='free':
        raise RuntimeError('Free-plan experiment must not probe a different entitlement')
    for filename,endpoint,symbol,params in [
        ('SPY_US_eod.json','eod','SPY.US',{'from':'2021-01-01','to':'2026-09-30'}),
        ('US_active_symbols.json','exchange-symbol-list','US',{}),
        ('US_delisted_symbols.json','exchange-symbol-list','US',{'delisted':1})]:
        path=OUT/filename
        if path.exists():continue
        payload=client.get(endpoint,symbol,**params)
        if endpoint=='eod':payload=validate_prices(payload)
        elif not isinstance(payload,list):raise ValueError('Unexpected symbol list')
        path.write_text(json.dumps(payload))
    account=client.get('user')
    safe={k:account[k]for k in ('subscriptionType','apiRequests','apiRequestsDate','dailyRateLimit','extraLimit')if k in account}
    quota=usage_summary(account)
    if not quota['quota_date_is_current']:quota['remaining_units_today']=None
    (OUT/'account_final.json').write_text(json.dumps({'account_fields':safe,'quota':quota},indent=2)+'\n')
    return {'status':'COMPLETE','reserved_account_units':3}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-pilot',action='store_true',help='Explicit bounded free-account SPY/catalogue probe')
    args=parser.parse_args()
    if args.account_pilot:
        print(json.dumps(account_pilot()));return
    requests=[('eod','AAPL.US'),('eod','AMZN.US'),('eod','TSLA.US'),
              ('splits','AAPL.US'),('div','AAPL.US'),
              ('fundamentals','AAPL.US'),('fundamentals','AMZN.US'),('fundamentals','TSLA.US'),
              ('eod','EURUSD.FOREX')]
    for endpoint,symbol in requests:
        p=recover_demo(endpoint,symbol)
        print(symbol,endpoint,'cached' if p else 'unavailable')


if __name__=='__main__':main()
