"""Offline recovery audit and sourced current-GICS overlays; no portfolio replay."""
from __future__ import annotations
import csv,gzip,hashlib,json,re
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from functools import lru_cache
import exchange_calendars as xc
from research.spgm_sources import DEFAULT_OUTPUT,ROOT
from research.spgm_proxy import isin_valid
from research.spgm_data_completeness import REPO,REQUIREMENTS,valid_bar,write_csv
from research.eodhd_probe import validate_prices
from research.corporate_actions import price_flags
from research.classification_policy import resolve_sector,EXPLORATORY_CURRENT_GICS,STRICT_PIT,SECTORS

OUT=DEFAULT_OUTPUT/'historical_backtest/recovery_316'
BASE=DEFAULT_OUTPUT/'historical_backtest/data_completeness'
START,END='2021-01-01','2026-09-30'
NEEDS={'momentum63':64,'momentum126':127,'momentum252':253,'ema200_minimum':200,'atr14_minimum':15}
MIC={'NASDAQ':'XNAS','NYSE':'XNYS','NYSE ARCA':'ARCX','NYSEARCA':'ARCX','BATS':'BATS','KO':'XKRX','TW':'XTAI'}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def name_key(s):return re.sub('[^A-Z0-9]','',s.upper())


@lru_cache(None)
def expected_sessions(calendar):
    # XNAS uses the installed XNYS-equivalent US session calendar. This is a
    # dated-price diagnostic, not proof of a historical Nasdaq listing.
    cal=xc.get_calendar('XNYS' if calendar=='XNAS' else calendar)
    days={d.date().isoformat() for d in cal.sessions_in_range(START,END)}
    if calendar=='XTAI':days.discard('2026-07-10') # preserved supplied evidence
    return sorted(days)


def gap_audit(rows,calendar,cutoffs):
    expected=expected_sessions(calendar)
    dates={r['date']for r in rows if valid_bar(r) and START<=r['date']<=END}
    if calendar=='XTAI':dates.discard('2026-07-10')
    missing=sorted(set(expected)-dates);unexpected=sorted(dates-set(expected))
    result=[]
    for cutoff in sorted(set(cutoffs)):
        sessions=[d for d in expected if d<=cutoff]
        actual=dates&set(sessions)
        gaps={k:sorted(set(sessions[-n:])-actual) for k,n in NEEDS.items()}
        result.append(dict(cutoff=cutoff,available_prior_bars=len(actual),
            missing_by_input={k:len(v)for k,v in gaps.items()},missing_dates=gaps,
            count_minimum_met={k:len(actual)>=n for k,n in NEEDS.items()},
            seed_history_missing=len(set(sessions)-actual)))
    return dict(expected=len(expected),valid_target_dates=len(dates),missing_dates=missing,
                unexpected_dates=unexpected,cutoffs=result)


def provider_candidates(row,index):
    ids=[v for v in row['isin'].split(';') if isin_valid(v)]
    matches=[x for i in ids for x in index.get(i,[])]
    signatures={(x['Code'],x['_suffix'],x.get('Exchange'),x.get('Currency'),x.get('Type'))for x in matches}
    return matches,len(signatures)


def build_current_sector(row,matches,sec,gics,demo_general):
    """Exact provider ISIN -> unique current symbol -> SEC CIK -> sourced GICS.

    No name-only joins and no SIC/NAICS conversions. Older archive tickers are
    kept as evidence, never used to assert a historical listing interval.
    """
    active=[r for r in matches if r['_kind']=='active' and r['_suffix']=='US'
            and r.get('Isin') in row['isin'].split(';') and r.get('Type')=='Common Stock']
    symbols={r['Code']for r in active}
    if len(symbols)!=1:return None
    symbol=next(iter(symbols));s=sec.get(symbol);g=gics.get(symbol)
    if not s or not g or str(s['cik']).lstrip('0')!=g['CIK'].lstrip('0') or g.get('GICS Sector') not in SECTORS:return None
    general=demo_general.get(symbol)
    if general:
        if general.get('ISIN') not in row['isin'].split(';'):raise ValueError('Demo identifier mismatch')
        if general.get('GicSector') and general['GicSector']!=g['GICS Sector']:raise ValueError('Current GICS sources conflict')
        if general.get('CIK') and str(general['CIK']).lstrip('0')!=str(s['cik']).lstrip('0'):raise ValueError('Current issuer identity conflict')
        if general.get('CUSIP') and row.get('cusip') and general['CUSIP'] not in row['cusip'].split(';'):raise ValueError('Current share-class identity conflict')
    source_manifest=json.loads((DEFAULT_OUTPUT/'historical_backtest/reference_sources/retrieval_manifest.json').read_text())
    observed=next(x['retrieved_at']for x in source_manifest if x.get('file')=='current_sp500.csv')
    record=dict(instrument_key=row['instrument_key'],sector=g['GICS Sector'],sector_scheme='GICS',
        source_url='https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv',
        retrieved_at=observed,classification_asof=observed,
        taxonomy_version='source snapshot '+sha(DEFAULT_OUTPUT/'historical_backtest/reference_sources/current_sp500.csv')+'; GICS 11-sector labels; underlying release not supplied',
        identity_ambiguous=False,
        approximation_reason='Current sector applied retrospectively; historical taxonomy release and past sector truth not established')
    proof=dict(record=record,identity_chain=dict(isin=row['isin'],provider_records=active,
        sec_current_record=s,gics_current_record=g),
        evidence_sources={str((OUT/'US_active_symbols.json').relative_to(OUT)):sha(OUT/'US_active_symbols.json'),
            'public_sources/sec_tickers.html':sha(OUT/'public_sources/sec_tickers.html'),
            '../reference_sources/current_sp500.csv':sha(DEFAULT_OUTPUT/'historical_backtest/reference_sources/current_sp500.csv')},
        rights='SEC public bulk data; existing source data package ODC-PDDL-1.0; EODHD personal research, raw records not redistributed',
        limitation='Current exact-ID provider assertion still requires historical listing/share-representation verification for prices')
    file=OUT/'sector_evidence'/(row['instrument_key'].replace(':','_')+'.json');dump(file,proof)
    record.update(evidence_file=str(file.relative_to(OUT)),sha256=sha(file))
    return dict(instrument_key=row['instrument_key'],current_gics=record,historical_gics_corrections=[])


def run():
    inventory=BASE/'SPGM_DATA_COMPLETENESS_INVENTORY.csv'
    original_summary=json.loads((BASE/'summary.json').read_text())
    if sha(inventory)!=original_summary['inventory_sha256']:raise ValueError('Original inventory drift')
    with inventory.open()as f:all_rows=list(csv.DictReader(f))
    cohort=[r for r in all_rows if r['status']=='PARTIALLY_READY']
    if len(cohort)!=316:raise ValueError('Expected original fixed 316 cohort')
    raw_hashes={str(inventory):sha(inventory)}
    with gzip.open(REPO/'backtests/staged/wf3_prices.json.gz','rt')as f:legacy=json.load(f)
    source=REPO/'backtests/staged/wf3_prices.json.gz';raw_hashes[str(source)]=sha(source)
    index=defaultdict(list)
    for filename,suffix,kind in [('US_active_symbols.json','US','active'),('US_delisted_symbols.json','US','delisted')]:
        path=OUT/filename;raw_hashes[str(path)]=sha(path)
        for r in json.loads(path.read_text()):
            if isin_valid(r.get('Isin')or''):index[r['Isin']].append(r|{'_suffix':suffix,'_kind':kind,'_source_file':str(path)})
    for suffix in ('KO','TW'):
        path=ROOT/'asia_corporate_actions'/(suffix+'_symbols.json');raw_hashes[str(path)]=sha(path)
        for r in json.loads(path.read_text()):
            if isin_valid(r.get('Isin')or''):index[r['Isin']].append(r|{'_suffix':suffix,'_kind':'active','_source_file':str(path)})
    sec_data=json.loads((OUT/'public_sources/sec_tickers.html').read_text());sec={}
    for values in sec_data['data']:
        r=dict(zip(sec_data['fields'],values))
        if r['ticker'] in sec:sec[r['ticker']]=None # duplicate current ticker excluded
        else:sec[r['ticker']]=r
    gics={}
    with (DEFAULT_OUTPUT/'historical_backtest/reference_sources/current_sp500.csv').open()as f:
        for r in csv.DictReader(f):gics[r['Symbol']]=r
    demo_general={}
    for symbol in ('AAPL','AMZN','TSLA'):
        path=OUT/'demo'/(symbol+'_US_fundamentals.json')
        if path.exists():demo_general[symbol]=json.loads(path.read_text())
    prelaunch_ids=set()
    p=DEFAULT_OUTPUT/'sec_only_decision_universe/2023-09_confirmed.csv.gz'
    with gzip.open(p,'rt')as f:
        for r in csv.DictReader(f):prelaunch_ids.update([r['isin'],r['cusip']])
    listing_pilot=json.loads((OUT/'sec_listing_pilot/manifest.json').read_text())
    listing_points={e['symbol']:e.get('cover',{})for e in listing_pilot}
    id_links={}
    for entry in json.loads((OUT/'id_mapping_pilot.json').read_text()):
        if entry.get('status')=='retrieved':
            payload=json.loads(Path(entry['file']).read_text())
            id_links[entry['isin']]=payload.get('data',[])
            if payload.get('links',{}).get('next'):raise ValueError('Identifier response pagination incomplete')
    rows,detail,overlays=[],{},[]
    for r in cohort:
        matches,signatures=provider_candidates(r,index)
        supplemental=[x for i in r['isin'].split(';')for x in id_links.get(i,[])if x.get('isin')==i]
        overlay=build_current_sector(r,matches,sec,gics,demo_general)
        if overlay:overlays.append(overlay)
        symbol=r['observed_tickers'];series=[]
        for e in json.loads(r['price_evidence']):
            path=REPO/e['source']
            if not path.exists():continue
            if e['source_section']=='market':data=legacy['market'][e['symbol']]['rows']
            else:
                with path.open()as f:data=[{k:(v if k=='date'else float(v))for k,v in x.items()}for x in csv.DictReader(f)]
            series.append((e['symbol'],data,e['source'],sha(path)))
            raw_hashes[str(path)]=sha(path)
        recovered=False
        demo_path=OUT/'demo'/(symbol+'_US_eod.json')
        if symbol in demo_general and demo_path.exists():
            general=demo_general[symbol]
            if general.get('ISIN') not in r['isin'].split(';'):raise ValueError('Price demo identity mismatch')
            data=validate_prices(json.loads(demo_path.read_text()))
            series.append((symbol+'.US',data,str(demo_path.relative_to(REPO)),sha(demo_path)));recovered=True
        if not series:raise ValueError('Original partial cohort unexpectedly has no bars')
        best=max(series,key=lambda s:sum(START<=x['date']<=END for x in s[1]))
        calendar='XKRX' if r['trading_currency']=='KRW' else 'XTAI' if r['trading_currency']=='TWD' else 'XNYS'
        membership=json.loads(r['membership_evidence'])
        cutoffs=[m['selection_cutoff_utc'][:10]for m in membership]
        if any(v in prelaunch_ids for k in ('isin','cusip')for v in r[k].split(';')if v):cutoffs.append('2023-09-29')
        gaps=gap_audit(best[1],calendar,cutoffs)
        before_series=[s for s in series if not (recovered and s[2]==str(demo_path.relative_to(REPO)))]
        before=max(before_series,key=lambda s:len(s[1]))
        before_gaps=gap_audit(before[1],calendar,cutoffs)
        old_prices={b['date']:b for b in before[1]}
        new_prices={b['date']:b for b in best[1]}
        overlapping=sorted(set(old_prices)&set(new_prices)) if recovered else []
        close_deltas=[abs(float(new_prices[d]['close'])/float(old_prices[d]['close'])-1)*100 for d in overlapping]
        legacy_actions=legacy['market'].get(symbol,{})
        dividend_file=OUT/'demo'/(symbol+'_US_div.json')
        split_file=OUT/'demo'/(symbol+'_US_splits.json')
        recovered_dividends=json.loads(dividend_file.read_text()) if dividend_file.exists() else []
        recovered_splits=json.loads(split_file.read_text()) if split_file.exists() else []
        verified=json.loads((REPO/'research/verified_quality_evidence.json').read_text())['market_returns']
        anomaly_flags=price_flags(best[1],verified_returns=verified.get(best[0])) if all('adjusted_close'in b for b in best[1]) else []
        d=dict(best_symbol=best[0],calendar_basis=calendar,gaps=gaps,before_recovery=before_gaps,
            cached_overlap_validation=dict(comparable_raw_coordinate_not_independently_verified=True,
                shared_sessions=len(overlapping),max_close_difference_pct=max(close_deltas,default=None)),
            historical_listing_point=listing_points.get(symbol),
            corporate_action_fragments=dict(legacy_splits=legacy_actions.get('splits',[]),
                legacy_dividends=legacy_actions.get('dividends',[]),
                demo_split_query_completed=split_file.exists(),demo_splits=recovered_splits,
                demo_dividend_query_completed=dividend_file.exists(),demo_dividends=recovered_dividends,
                price_anomalies=anomaly_flags,complete_material_event_ledger_verified=False),
            sources=[dict(symbol=s[0],file=s[2],sha256=s[3],observations=len(s[1]),
                first=min(x['date']for x in s[1]),last=max(x['date']for x in s[1]))for s in series],
            provider_current_and_delisted_candidates=matches,supplemental_id_mapping_candidates=supplemental,sector_overlay=overlay)
        detail[r['instrument_key']]=d
        # Current classifications pass the existing exploratory sector resolver;
        # strict classifications and historically dated listing gates remain.
        sector_pass=False
        if overlay:
            for m in membership:
                resolve_sector(m|{'instrument_key':r['instrument_key']}|overlay,datetime.fromisoformat(m['selection_cutoff_utc']),EXPLORATORY_CURRENT_GICS)
            sector_pass=True
        flags={k:r[k+'_pass']=='True'for k in REQUIREMENTS}
        flags['gics']=sector_pass
        # Complete session span is a repaired fragment, not an admission bypass:
        # open/close/availability, verified MIC intervals and adjustment/action
        # coordinates remain missing from source rows and the input bundle.
        missing=[k for k in REQUIREMENTS if not flags[k]]
        first=gaps['cutoffs'][0]
        rows.append(dict(instrument_key=r['instrument_key'],name=r['name'],isin=r['isin'],cusip=r['cusip'],sedol=r['sedol'],
            country=r['country'],original_status='PARTIALLY_READY',status='PARTIALLY_READY',
            membership_months=r['membership_months'],first_selection_month=r['first_selection_month'],
            last_selection_month=r['last_selection_month'],original_inventory_sha256=original_summary['inventory_sha256'],
            existing_symbols=r['observed_tickers']or r['current_exchange_symbols'],
            provider_exact_isin_candidate=bool(matches),provider_listing_signatures=signatures,
            provider_any_identifier_candidate=bool(matches or supplemental),
            supplemental_id_mapping_symbols=';'.join(x.get('symbol','')for x in supplemental),
            supplemental_id_mapping_verified_historical_primary=False,
            current_mic_candidates=';'.join(sorted({MIC.get(m.get('Exchange'),'UNRESOLVED:'+str(m.get('Exchange')))for m in matches})),
            trading_currency_candidates=';'.join(sorted({m.get('Currency','')for m in matches})),
            historical_listing_verified=False,listing_interval_ready=False,
            dated_sec_listing_observation=listing_points.get(symbol,{}).get('status')==200,
            dated_sec_listing_source=listing_points.get(symbol,{}).get('source_url',''),
            dated_sec_listing_filing_date=listing_points.get(symbol,{}).get('filing',{}).get('filingDate',''),
            recovered_vs_cached_overlap_sessions=len(overlapping),
            recovered_vs_cached_max_close_difference_pct=max(close_deltas,default=''),
            best_price_symbol=best[0],first=min(x['date']for x in best[1]),last=max(x['date']for x in best[1]),
            valid_rows=sum(valid_bar(x)for x in best[1]),expected_2021_sessions=gaps['expected'],
            missing_2021_sessions=len(gaps['missing_dates']),unexpected_sessions=len(gaps['unexpected_dates']),
            missing_through_last_membership_cutoff=gaps['cutoffs'][-1]['seed_history_missing'],
            missing_during_observed_membership_months=sum(d[:7] in r['membership_months'].split(';')for d in gaps['missing_dates']),
            initial_cutoff=first['cutoff'],initial_available_bars=first['available_prior_bars'],
            **{k+'_initial_missing':v for k,v in first['missing_by_input'].items()},
            initial_ema_seed_missing=first['seed_history_missing'],
            price_span_recovered=recovered and not gaps['missing_dates'] and not gaps['unexpected_dates'],
            gics_exploratory_pass=sector_pass,gics_strict_pass=False,
            sector=overlay['current_gics']['sector']if overlay else 'UNRESOLVED',
            sector_approximation=sector_pass,sector_source=overlay['current_gics']['source_url']if overlay else '',
            sector_sha256=overlay['current_gics']['sha256']if overlay else '',
            calendar_diagnostic=calendar,calendar_admission_pass=False,
            adjusted_close_candidate=any(any('adjusted_close'in b for b in s[1])for s in series),
            legacy_split_record_count=len(legacy_actions.get('splits',[])),
            legacy_dividend_record_count=len(legacy_actions.get('dividends',[])),
            recovered_split_query_completed=split_file.exists(),
            recovered_split_record_count=len(recovered_splits),
            recovered_dividend_record_count=len(recovered_dividends),
            recovered_dividends_with_payment_date=sum(bool(x.get('paymentDate'))for x in recovered_dividends),
            complete_merger_delisting_ledger=False,price_flags_requiring_review=sum(x['requires_review']for x in anomaly_flags),
            price_flag_dates=';'.join(x['date']for x in anomaly_flags),
            current_adr_primary_category=demo_general.get(symbol,{}).get('HomeCategory','UNVERIFIED; preserve source share class'),
            missing_requirements=';'.join(missing),
            required_actions='verify prior-public listing intervals and security representation; validate source clocks/calendars; '
                'reconcile split-only OHLC, total-return vintages, dividends/payment dates and merger/delisting ledger; '
                +('recover seed/warm-up and missing sessions; 'if gaps['missing_dates']else'')
                +('source exact-ID current GICS and corrections; 'if not sector_pass else'disclose current-GICS approximation and assess sensitivity; ')
                +('source native-USD FX with historical publication times'if not flags['fx']else'USD identity FX only'),
            source_evidence=json.dumps(d['sources'],separators=(',',':')),
            **{k+'_pass':v for k,v in flags.items()}))
    write_csv(REPO/'research/SPGM_316_RECOVERY_INVENTORY.csv',rows)
    dump(OUT/'security_recovery_details.json',detail)
    dump(OUT/'classification_records.json',overlays)
    # Verified doc capabilities do not imply historical contract/price coverage.
    provider_counts={}
    for label,denom in [('priority316',cohort),('all4236',all_rows)]:
        counts=Counter();unmapped=[]
        for r in denom:
            matches,n=provider_candidates(r,index)
            counts['exact_isin_candidates']+=bool(matches)
            counts['one_listing_signature']+=n==1
            counts['multiple_listing_signatures']+=n>1
            if not matches:unmapped.append(dict(instrument_key=r['instrument_key'],name=r['name']))
        provider_counts[label]=dict(denominator=len(denom),**counts,unmapped=unmapped)
    references=[]
    for symbol in ['SPY']+sorted(legacy['sector_etfs']):
        if symbol=='SPY':p=OUT/'SPY_US_eod.json';data=json.loads(p.read_text()) if p.exists()else[]
        else:data=legacy['sector_etfs'][symbol]['rows']
        gap=gap_audit(data,'XNYS',['2023-09-29'])
        references.append(dict(symbol=symbol,rows=len(data),first=min((x['date']for x in data),default=''),
            last=max((x['date']for x in data),default=''),prelaunch=sum(x['date']<='2023-09-29'for x in data),
            required_prelaunch=254 if symbol=='SPY' else 253,
            missing_2021_sessions=len(gap['missing_dates']),full_ready=False,
            missing_input_schema_fields=['verified_historical_MIC_currency','total_return_close_basis',
                'split_adjusted_OHLC_provenance','open_at','close_at','available_at',
                'dividend_and_material_action_ledger','full_warmup']))
    dump(OUT/'reference_validation.json',references)
    summary=dict(original_partial=316,fully_ready=0,remaining_partial=316,
        recovered_full_session_spans=sum(r['price_span_recovered']for r in rows),
        repaired_price_names=[r['name']for r in rows if r['price_span_recovered']],
        supplemental_identity_probes=id_links,
        priority_any_provider_identifier_candidates=sum(r['provider_any_identifier_candidate']for r in rows),
        all_any_provider_identifier_candidates=provider_counts['all4236']['exact_isin_candidates']+sum(not provider_candidates(r,index)[0] and bool(id_links.get(r['isin']))for r in all_rows),
        current_gics_backfills=sum(r['gics_exploratory_pass']for r in rows),
        verified_historical_sectors=0,provider_candidates=provider_counts,
        country_counts=dict(Counter(r['country']for r in rows)),
        sector_counts=dict(Counter(r['sector']for r in rows)),
        original_initial_shortfalls={k:sum(d['before_recovery']['cutoffs'][0]['missing_by_input'][k]>0 for d in detail.values())for k in NEEDS},
        remaining_initial_shortfalls={k:sum(d['gaps']['cutoffs'][0]['missing_by_input'][k]>0 for d in detail.values())for k in NEEDS},
        current_gics_country_counts=dict(Counter(r['country']for r in rows if r['gics_exploratory_pass'])),
        current_gics_approximation_security_months=sum(len(json.loads(r['membership_evidence']))for r in cohort if r['instrument_key']in {o['instrument_key']for o in overlays}),
        current_gics_covered_securities=len(overlays),
        original_initial_252_gaps=dict(Counter(d['before_recovery']['cutoffs'][0]['missing_by_input']['momentum252']for d in detail.values())),
        reference_inputs=references,account=json.loads((OUT/'account_final.json').read_text()),
        account_request_cost=json.loads((OUT/'eodhd_request_ledger.json').read_text())['reserved_units'],
        public_demo_requests=len(json.loads((OUT/'demo_request_manifest.json').read_text())),
        raw_input_hashes=raw_hashes,no_backtest_executed=True)
    dump(OUT/'summary.json',summary)
    for path,value in raw_hashes.items():
        if sha(Path(path))!=value:raise ValueError('Original/recovered input changed')
    print(json.dumps({k:v for k,v in summary.items()if k not in ['provider_candidates','reference_inputs','raw_input_hashes','account']},indent=2))
    return summary


if __name__=='__main__':run()
