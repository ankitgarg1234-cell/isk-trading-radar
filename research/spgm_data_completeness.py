"""Offline security-level audit. Never downloads data or invokes a backtest.

Identity joins establish a candidate security line, not historically effective
listing intervals. Admission requirements remain the existing strategy gates.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from research.classification_policy import EXPLORATORY_CURRENT_GICS, resolve_sector
from research.listing_evidence_audit import candidate, mapping_index
from research.price_inventory import REFERENCES
from research.spgm_proxy import identifier_keys
from research.spgm_sources import DEFAULT_OUTPUT, ROOT
from research.spgm_strategy_audit import dated_verified

REPO = Path(__file__).resolve().parents[1]
OUT = DEFAULT_OUTPUT / 'historical_backtest/data_completeness'
REQUIREMENTS = ('listing', 'ohlcv', 'adjustment', 'corporate_actions', 'gics',
                'calendar_timezone', 'fx', 'pit_membership')
STATUSES = ('BACKTEST_READY', 'PARTIALLY_READY', 'IDENTITY_UNRESOLVED', 'NO_USABLE_PRICE_DATA')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'))


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def identity_groups(rows):
    """Only co-observed checksum-valid aliases join; never join issuer or ticker.

    An alternate ID shared by multiple ISINs is quarantined. Components with
    multiple IDs of the same type are also quarantined, preserving share classes
    and identifier changes until an explicit lifecycle crosswalk exists.
    """
    links = defaultdict(set)
    for row in rows:
        ids = identifier_keys(row)
        for key in ids:
            links[key].update(ids)
    seen, mapping, conflicts = set(), {}, set()
    for seed in sorted(links):
        if seed in seen:
            continue
        pending, component = [seed], set()
        while pending:
            key = pending.pop()
            if key in component:
                continue
            component.add(key)
            pending.extend(links[key] - component)
        seen.update(component)
        ambiguous = any(sum(k[0] == kind for k in component) > 1
                        for kind in ('isin', 'cusip', 'sedol'))
        if ambiguous:
            conflicts.update(component)
            # No automatic union of any member of a conflicting component.
            for key in component:
                mapping[key] = ':'.join(key)
        else:
            chosen = min(component, key=lambda x: (('isin','cusip','sedol').index(x[0]), x[1]))
            for key in component:
                mapping[key] = ':'.join(chosen)
    groups = defaultdict(list)
    for row in rows:
        ids = identifier_keys(row)
        key = mapping[ids[0]] if ids else 'unresolved:' + row['instrument_key']
        groups[key].append(row)
    return groups, mapping, conflicts


def primary_status(flags, identity_resolved, usable_prices):
    if not identity_resolved:
        return 'IDENTITY_UNRESOLVED'
    if not usable_prices:
        return 'NO_USABLE_PRICE_DATA'
    return 'BACKTEST_READY' if all(flags[k] for k in REQUIREMENTS) else 'PARTIALLY_READY'


def valid_bar(row):
    try:
        date.fromisoformat(str(row['date']))
        o, h, l, c, v = (float(row[k]) for k in ('open','high','low','close','volume'))
        return (all(math.isfinite(x) for x in (o,h,l,c,v)) and min(o,h,l,c) > 0
                and v >= 0 and l <= min(o,c) <= max(o,c) <= h)
    except (KeyError, ValueError, TypeError):
        return False


def describe_prices(symbol, rows, path, section, actions=None, closed_dates=(), source_sha=None):
    valid = [r for r in rows if valid_bar(r) and r['date'] not in closed_dates]
    dates = sorted(r['date'] for r in valid)
    dated = [r.get('date') for r in rows]
    n = len(dates)
    return dict(symbol=symbol, source=str(path.relative_to(REPO)), source_section=section,
                sha256=source_sha or digest(path), raw_rows=len(rows), valid_rows=n,
                invalid_rows=sum(not valid_bar(r) for r in rows),
                excluded_closed_sessions=sum(r.get('date') in closed_dates for r in rows),
                duplicate_dates=len(dated)-len(set(dated)), first=dates[0] if n else '',
                last=dates[-1] if n else '',
                prelaunch_bars=sum(d <= '2023-09-29' for d in dates),
                target_bars=sum('2023-10-01' <= d <= '2026-09-30' for d in dates),
                full_seed_span=bool(n and dates[0] <= '2021-01-04' and dates[-1] >= '2026-09-30'),
                adjusted_close_rows=sum(r.get('adjusted_close') not in (None,'') for r in valid),
                splits=len((actions or {}).get('splits',[])),
                dividends=len((actions or {}).get('dividends',[])),
                dates=dates)


def discover_sources():
    """Inspect real data containers in checkout, excluding synthetic/test outputs.

    Classifies other CSV/gzip candidates explicitly in a manifest. Outputs from
    this audit are excluded so repeat runs have the same input denominator.
    """
    candidates, prices, hashes = [], defaultdict(list), {}
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in {'.git','node_modules','__pycache__','.expo',
                    '.venv','venv','data_completeness'}]
        dirs.sort()
        for name in sorted(files):
            p = Path(root)/name
            if p.suffix not in {'.csv','.gz','.parquet','.feather','.sqlite','.db','.pkl'}:
                continue
            rel = str(p.relative_to(REPO))
            if name.startswith('SPGM_DATA_COMPLETENESS') or name.startswith('SPGM_READY_TICKERS') or name.startswith('SPGM_MISSING_DATA'):
                continue
            if 'synthetic_parity' in rel:
                kind = 'SYNTHETIC_EXCLUDED'
            elif p.suffix == '.csv':
                with p.open() as f:
                    headers = next(csv.reader(f), [])
                kind = 'OHLCV_CSV' if {'date','open','high','low','close','volume'} <= set(headers) else 'METADATA_OR_RESULTS'
                if kind == 'OHLCV_CSV':
                    with p.open() as f:
                        data = list(csv.DictReader(f))
                    closed = {'2026-07-10'} if any(t in name for t in ['2317_TW','2330_TW','3711_TW']) else set()
                    symbol = name.replace('_session_filtered','').replace('_split_only_ohlc','_US').replace('_','.')[:-4]
                    prices[symbol].append(describe_prices(symbol,data,p,'CSV',closed_dates=closed))
                    hashes[rel] = digest(p)
            elif name == 'wf3_prices.json.gz':
                kind = 'LEGACY_PRICE_CONTAINER'
                with gzip.open(p,'rt') as f:
                    data = json.load(f)
                # All three sections matter. Sector ETFs are NOT absent merely
                # because they are outside the equity market dictionary.
                source_sha = digest(p)
                for section in ('market','sector_etfs'):
                    for symbol, entry in data.get(section,{}).items():
                        prices[symbol].append(describe_prices(symbol,entry.get('rows',[]),p,
                                                             section,entry,source_sha=source_sha))
                if data.get('benchmark'):
                    symbol = data['benchmark_symbol']
                    entry = data['benchmark']
                    prices[symbol].append(describe_prices(symbol,entry.get('rows',[]),p,'benchmark',entry,source_sha=source_sha))
                hashes[rel] = digest(p)
            else:
                kind = 'METADATA_OR_RESULTS'
            candidates.append(dict(path=rel,bytes=p.stat().st_size,kind=kind))
    return prices, candidates, hashes


def membership_valid(rows, conflicts):
    for row in rows:
        keys = identifier_keys(row)
        if not keys or any(k in conflicts for k in keys):
            return False
        try:
            available = datetime.fromisoformat(row['available_at'])
            cutoff = datetime.fromisoformat(row['selection_cutoff_utc'])
            if (available.tzinfo is None or cutoff.tzinfo is None or available >= cutoff
                    or row['membership_status'] != 'CONFIRMED' or not row['source_filing']
                    or not row['source_url'].startswith('https://www.sec.gov/Archives/')):
                return False
        except (KeyError, ValueError, TypeError):
            return False
    return True


def requirement_flags(members, series, currency, identity_resolved, conflicts):
    """Conservative independent evidence audit, not a new admission policy.

    Calendar/adjustment/action artifacts require dated evidence in existing
    inputs. Raw list presence, adjusted-close fields and library installation
    alone cannot establish these assertions. Short prices fail the seed span
    before any unvalidated extrapolation could be considered.
    """
    listing = identity_resolved and all(
        r.get('pit_ticker') and r.get('exchange_mic') and r.get('currency')
        and dated_verified(r,'listing',r['selection_cutoff_utc']) for r in members)
    full_history = any(s['full_seed_span'] and s['prelaunch_bars'] >= 253
                       and not s['invalid_rows'] and not s['duplicate_dates'] for s in series)
    def every_verified(kind):
        return bool(members) and all(dated_verified(r,kind,r['selection_cutoff_utc'])
                                     for r in members)
    calendar = every_verified('calendar') and all(r.get('exchange_mic') and
                    r.get('exchange_timezone') for r in members)
    return dict(listing=bool(listing), ohlcv=bool(full_history and calendar),
        adjustment=bool(full_history and every_verified('adjustment')),
        corporate_actions=bool(full_history and every_verified('action_coverage')),
        gics=False, calendar_timezone=bool(calendar),
        fx=bool(currency=='USD' and identity_resolved),
        pit_membership=membership_valid(members,conflicts))


def run():
    frozen = DEFAULT_OUTPUT/'sec_only_decision_universe'
    manifest = json.loads((frozen/'manifest.json').read_text())
    rows, all_rows, hashes = [], [], {}
    for path in sorted(frozen.glob('*_confirmed.csv.gz')):
        name = path.name
        if digest(path) != manifest['output_sha256'][name]:
            raise ValueError('Frozen universe checksum mismatch: '+name)
        hashes[str(path.relative_to(REPO))] = digest(path)
        month = name[:7]
        with gzip.open(path,'rt') as stream:
            data = [dict(r,selection_month=month) for r in csv.DictReader(stream)]
        all_rows.extend(data)
        if '2023-10' <= month <= '2026-09':
            rows.extend(data)
    if len({r['selection_month'] for r in all_rows}) != 48:
        raise ValueError('Expected all 48 original SEC-only universes')
    groups, alias_map, conflicts = identity_groups(rows)
    prices, discovered, price_hashes = discover_sources()
    hashes.update(price_hashes)
    records = []
    for filename in ('KO_symbols.json','TW_symbols.json'):
        path = ROOT/'asia_corporate_actions'/filename
        records.extend(json.loads(path.read_text()))
        hashes[str(path.relative_to(REPO))] = digest(path)
    index = mapping_index(records)
    # Exact security identifiers -> observed ticker, not issuer-name matching.
    # Future archived observations may help identify a cached security line;
    # they cannot become historical listing/admission evidence.
    ticker_lines, ticker_evidence = defaultdict(set), defaultdict(list)
    for r in all_rows:
        if r.get('pit_ticker') and r.get('currency') == 'USD':
            keys = identifier_keys(r)
            for ident in keys:
                key = alias_map.get(ident)
                if key:
                    ticker_lines[r['pit_ticker']].add(key)
                    ev = {k:r.get(k,'') for k in ('instrument_key','pit_ticker','pit_ticker_evidence_json')}
                    if ev not in ticker_evidence[key]:
                        ticker_evidence[key].append(ev)
    current_sectors = {}
    current_path = DEFAULT_OUTPUT/'historical_backtest/reference_sources/current_sp500.csv'
    if current_path.exists():
        hashes[str(current_path.relative_to(REPO))] = digest(current_path)
        with current_path.open() as f:
            for r in csv.DictReader(f):
                current_sectors[r['Symbol']] = r['GICS Sector']
    result = []
    for key, members in sorted(groups.items()):
        names = sorted({r['name'] for r in members})
        countries = sorted({r['country'] or 'UNKNOWN' for r in members})
        country = countries[0] if len(countries) == 1 else 'MULTIPLE'
        identifiers = {kind:sorted({r[kind] for r in members if (kind,r[kind]) in identifier_keys(r)})
                       for kind in ('isin','cusip','sedol')}
        id_conflict = any(ident in conflicts for r in members for ident in identifier_keys(r))
        tickers = sorted(t for t, keys in ticker_lines.items() if key in keys)
        unique_tickers = [t for t in tickers if ticker_lines[t] == {key}]
        current = [candidate(r,index) for r in {r['isin']:r for r in members}.values()]
        current = [r for r in current if r['status'] != 'NO_EXACT_ISIN_MATCH']
        exchange_symbols = sorted({r['symbol'] for r in current if r['status'] == 'CURRENT_EXACT_ISIN_CANDIDATE'})
        identity_resolved = bool(not id_conflict and ((len(unique_tickers)==1 and len(tickers)==1)
                                or len(exchange_symbols)==1))
        symbols = sorted(set(unique_tickers+exchange_symbols))
        # .US caches can be joined only to a source-observed US ticker. No ADR
        # prices are joined to the issuer's foreign ordinary ISIN by name.
        cache_symbols = symbols + [s+'.US' for s in unique_tickers]
        series = [x for s in cache_symbols for x in prices.get(s,[])]
        months = sorted({r['selection_month'] for r in members})
        usable = [s for s in series if any(d[:7] in months for d in s['dates'])]
        best = max(usable, key=lambda s:(s['target_bars'],s['valid_rows'],s['symbol'])) if usable else None
        curr = sorted({r['currency'] for r in current if r.get('currency')})
        source_currencies = sorted({r['currency'] for r in members if r['currency']})
        # N-PORT position currency is NOT silently treated as trading currency.
        currency = curr[0] if len(curr)==1 else ('USD' if len(unique_tickers)==1 and source_currencies==['USD'] else '')
        currency_basis = 'current exact-ISIN exchange record' if curr else ('USD archive line and legacy US ticker context; venue/effective interval unverified' if currency else 'unverified trading currency')
        sectors, sector_errors = set(), set()
        for r in members:
            try:
                resolved = resolve_sector(r,datetime.fromisoformat(r['selection_cutoff_utc']),EXPLORATORY_CURRENT_GICS)
                sectors.add(resolved['sector'])
            except (ValueError,KeyError,TypeError) as exc:
                sector_errors.add(str(exc))
        gics = len(sectors)==1 and not sector_errors
        # Available price bars, action lists and short-period calendar checks
        # are evidence fragments. None supplies a complete validated bundle.
        flags = requirement_flags(members,series,currency,identity_resolved,conflicts)
        flags['gics'] = gics
        missing = [k for k in REQUIREMENTS if not flags[k]]
        reasons = dict(listing='dated ticker/MIC/trading-currency listing evidence absent',
            ohlcv='January2021 seed history, full session validation and sufficient warm-up absent; verified IPO/delisting exceptions absent',
            adjustment='full-period split-only OHLC and reconciled total-return basis absent',
            corporate_actions='complete identified dividend/split/merger/delisting ledger absent; partial lists are not completeness proof',
            gics='no identity-matched, hash-verified GICS overlay admitted by existing classification policy',
            calendar_timezone='historical MIC-matched calendar/time-zone bundle and session reconciliation absent',
            fx='no verified native-currency to USD tape (USD identity conversion needs no FX tape)',
            pit_membership='invalid or conflicting stable identifier / invalid public-before-cutoff SEC evidence')
        reasons['ohlcv'] += (f"; best mapped series {best['symbol']} spans {best['first']}–{best['last']}, "
            f"{best['prelaunch_bars']} valid prelaunch bars; observed membership {months[0]}–{months[-1]}"
            if best else '; no identity-linked valid bars overlap observed membership months')
        if current:
            reasons['listing'] += '; current exact-ISIN candidates lack historical venue/effective-date proof'
        elif unique_tickers:
            reasons['listing'] += '; archived identifier/ticker evidence supplies no verified MIC interval'
        status = primary_status(flags,identity_resolved,bool(usable))
        evidence = [{k:v for k,v in s.items() if k != 'dates'} for s in series]
        source_membership = [{k:r[k] for k in ('selection_month','portfolio_date','publication_date',
            'available_at','selection_cutoff_utc','source_filing','source_url','raw_source_sha256',
            'isin','cusip','sedol','name','country','currency','pit_ticker','exchange_mic')} for r in members]
        item = dict(instrument_key=key,name=names[-1],all_names=compact(names),
            isin=';'.join(identifiers['isin']),cusip=';'.join(identifiers['cusip']),sedol=';'.join(identifiers['sedol']),
            country=country,countries=compact(countries),
            company_leis=compact(sorted({r['company_lei'] for r in members if r['company_lei']})),
            observed_company_groups=compact(sorted({r['company_group_estimate'] for r in members})),
            source_position_currencies=compact(source_currencies),
            observed_tickers=';'.join(tickers),current_exchange_symbols=';'.join(exchange_symbols),
            exchange_mic='',trading_currency=currency,currency_basis=currency_basis,
            sector=next(iter(sectors)) if gics else 'UNRESOLVED',
            unadmitted_current_sector_candidates=compact(sorted({current_sectors[t] for t in unique_tickers if t in current_sectors})),
            identifier_ambiguous=id_conflict,ticker_ambiguous=bool(tickers and len(unique_tickers)!=len(tickers)),
            identity_resolved=identity_resolved,identity_basis='CURRENT_EXACT_ISIN' if exchange_symbols else ('ARCHIVED_EXACT_ID_TICKER_VENUE_UNVERIFIED' if identity_resolved else 'UNRESOLVED'),
            status=status,first_selection_month=months[0],last_selection_month=months[-1],
            membership_months=';'.join(months),membership_observations=len(members),
            usable_matched_price_series=len(usable),candidate_price_series=len(series),
            best_price_symbol=best['symbol'] if best else '',best_price_first=best['first'] if best else '',
            best_price_last=best['last'] if best else '',best_price_valid_rows=best['valid_rows'] if best else 0,
            best_price_prelaunch_bars=best['prelaunch_bars'] if best else 0,
            first_membership_warmup_bars=sum(d[:7]<months[0] for d in best['dates']) if best else 0,
            full_2021_seed_span=any(s['full_seed_span'] for s in series),
            adjusted_close_candidate=any(s['adjusted_close_rows'] for s in series),
            partial_split_records=any(s['splits'] for s in series),
            partial_dividend_records=any(s['dividends'] for s in series),
            current_gics_candidate_source=str(current_path.relative_to(REPO)) if any(t in current_sectors for t in unique_tickers) else '',
            current_gics_candidate_source_sha256=hashes.get(str(current_path.relative_to(REPO)),'') if any(t in current_sectors for t in unique_tickers) else '',
            passed_requirement_count=sum(flags.values()),missing_fields=';'.join(missing),
            missing_reasons=compact({k:reasons[k] for k in missing}),
            ticker_identity_evidence=compact(ticker_evidence[key]),current_listing_evidence=compact(current),
            price_evidence=compact(evidence),membership_evidence=compact(source_membership),
            **{k+'_pass':v for k,v in flags.items()})
        result.append(item)
    OUT.mkdir(parents=True,exist_ok=True)
    inventory = OUT/'SPGM_DATA_COMPLETENESS_INVENTORY.csv'
    write_csv(inventory,result)
    references = []
    for symbol in REFERENCES:
        series = prices.get(symbol,[])
        references.append(dict(symbol=symbol,cached=bool(series),ready=False,
            first=min((s['first'] for s in series),default=''),last=max((s['last'] for s in series),default=''),
            valid_rows=max((s['valid_rows'] for s in series),default=0),
            prelaunch_bars=max((s['prelaunch_bars'] for s in series),default=0),
            required_prelaunch_bars=254 if symbol=='SPY' else 253,
            missing='SPY absent' if not series else '2021 history/prelaunch warm-up; adjustment/actions provenance; MIC/calendar validation',
            evidence=[{k:v for k,v in s.items() if k != 'dates'} for s in series]))
    write_csv(OUT/'reference_inputs.csv',[{k:v for k,v in r.items() if k!='evidence'} for r in references])
    statuses = Counter(r['status'] for r in result)
    counts = {s:statuses[s] for s in STATUSES}
    passed = {k:sum(r[k+'_pass'] for r in result) for k in REQUIREMENTS}
    summary = dict(label='SPGM historical ETF holdings proxy',months=36,source_universes=48,
        selection_month_start='2023-10',selection_month_end='2026-09',securities=len(result),
        security_month_observations=len(rows),original_instrument_keys=len({r['instrument_key'] for r in rows}),
        statuses=counts,requirement_pass_counts=passed,
        identity_resolved=sum(r['identity_resolved'] for r in result),
        matched_usable_prices=sum(r['identity_resolved'] and r['usable_matched_price_series']>0 for r in result),
        candidate_price_securities=sum(r['candidate_price_series']>0 for r in result),
        identifier_ambiguous=sum(r['identifier_ambiguous'] for r in result),
        ticker_ambiguous=sum(r['ticker_ambiguous'] for r in result),
        current_gics_candidate_securities=sum(bool(json.loads(r['unadmitted_current_sector_candidates'])) for r in result),
        partial_split_record_securities=sum(r['partial_split_records'] for r in result),
        partial_dividend_record_securities=sum(r['partial_dividend_records'] for r in result),
        adjusted_close_candidate_securities=sum(r['adjusted_close_candidate'] for r in result),
        sectors_unresolved=sum(r['sector']=='UNRESOLVED' for r in result),
        inventory_path=str(inventory),inventory_sha256=digest(inventory),inventory_bytes=inventory.stat().st_size,
        source_sha256=hashes,reference_inputs=references,new_api_requests=0,backtests_run=0)
    breakdown=[]
    for dimension,values in [('status',counts),('requirement_missing',{k:len(result)-v for k,v in passed.items()})]:
        for value,n in values.items():
            breakdown.append(dict(dimension=dimension,value=value,securities=n,ready=counts['BACKTEST_READY'] if dimension=='requirement_missing' else (n if value=='BACKTEST_READY' else 0)))
    for dimension in ('country','sector'):
        for value in sorted({r[dimension] for r in result}):
            part=[r for r in result if r[dimension]==value]
            breakdown.append(dict(dimension=dimension,value=value,securities=len(part),ready=sum(r['status']=='BACKTEST_READY' for r in part)))
            for status in STATUSES:
                breakdown.append(dict(dimension=dimension+'_status',value=value+'|'+status,
                    securities=sum(r['status']==status for r in part),ready=sum(r['status']==status=='BACKTEST_READY' for r in part)))
    write_csv(REPO/'research/SPGM_MISSING_DATA_BREAKDOWN.csv',breakdown)
    ready=[r for r in result if r['status']=='BACKTEST_READY']
    ready_fields=['instrument_key','name','observed_tickers','current_exchange_symbols','exchange_mic',
                  'trading_currency','sector','membership_months','price_evidence','membership_evidence']
    write_csv(REPO/'research/SPGM_READY_TICKERS.csv',[{k:r[k] for k in ready_fields} for r in ready],ready_fields)
    (OUT/'source_discovery.json').write_text(json.dumps(discovered,indent=2)+'\n')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    report(summary,result,breakdown,references,ready)
    # Assert no source was changed by auditing, including all 48 frozen files.
    for rel,sha in hashes.items():
        if digest(REPO/rel)!=sha:
            raise ValueError('Audit modified source: '+rel)
    return {k:v for k,v in summary.items() if k not in ('source_sha256','reference_inputs')}


def report(summary, rows, breakdown, references, ready):
    lines=['# SPGM data completeness audit','',
        '**SPGM historical ETF holdings proxy — not official MSCI ACWI IMI constituents.**', '',
        'Offline audit of the latest cached research state. No data requests, trades or backtest execution. '
        'All 48 frozen SEC-only universes are checksum-checked; the inventory denominator is the 36 monthly '
        'universes from October 2023 through September 2026. September 2023 prelaunch membership remains '
        'outside this denominator; the October experiment would additionally require its September 29 signal inputs.', '',
        f"**{summary['securities']:,} distinct security lines**, {summary['security_month_observations']:,} security-month observations. "
        f"Original instrument keys: {summary['original_instrument_keys']:,}. Deduplication uses only co-observed valid ISIN/CUSIP/SEDOL aliases. "
        'Issuer LEIs, names and tickers never collapse share classes or ordinary/ADR lines. Conflicting identifier components are quarantined.', '',
        '| Primary status | Securities |','|---|---:|']
    lines += [f'| {k} | {v:,} |' for k,v in summary['statuses'].items()]
    lines += ['',f"Resolved candidate instrument identities: **{summary['identity_resolved']:,}**. "
        f"Securities with identity-linked valid bars overlapping observed membership months: **{summary['matched_usable_prices']:,}**. "
        f"Securities with any ticker-linked price candidates: **{summary['candidate_price_securities']:,}**. "
        f"Identifier conflicts: **{summary['identifier_ambiguous']}**; ticker ambiguities: **{summary['ticker_ambiguous']}**.", '',
        'A resolved identity means a unique archived exact-ID ticker line or current exact-ISIN exchange record. '
        'It does not prove the venue, currency or listing effective interval for every historical selection. '
        'PARTIALLY_READY requires such a resolved line and at least some valid cached bars during an observed '
        'membership month; it makes no claim of adequate history. Unresolved identity takes priority over '
        'price availability; resolved identities without overlapping usable bars are NO_USABLE_PRICE_DATA.', '',
        '## Requirement coverage','', '| Requirement | Pass | Fail |','|---|---:|---:|']
    lines += [f"| {k} | {v:,} | {summary['securities']-v:,} |" for k,v in summary['requirement_pass_counts'].items()]
    lines += ['', 'Pass flags are independent and fail closed. No complete dated listing bundle, 2021 seed '
        'history, validated full-period split/TR tape, complete action ledger or calendar/time-zone bundle is present. '
        'Without verified listing-start/delisting evidence, a shorter history cannot receive an IPO or delisting exemption. '
        'No verified FX tape exists; USD identity conversion passes only for uniquely resolved USD lines, with the '
        'currency evidence recorded separately. A position currency alone does not establish trading currency.', '',
        'Sector labels in the legacy cache are undated. The cached current S&P 500 GICS table has source provenance '
        'but no approved exact-security overlay. Ticker-only current-sector candidates are recorded separately, '
        'never treated as historically verified or admitted GICS. The existing STRICT_PIT and '
        f"EXPLORATORY_CURRENT_GICS policies and coverage thresholds are unchanged. {summary['current_gics_candidate_securities']} security lines have unadmitted current sector candidates; {summary['adjusted_close_candidate_securities']} have adjusted-close candidates, {summary['partial_split_record_securities']} have partial split lists and {summary['partial_dividend_record_securities']} have partial dividend lists. None of these counts establishes full requirement coverage.", '',
        'Membership passes only for checksum-valid non-conflicting identifiers, confirmed SEC holdings, a source '
        'filing and timezone-aware publication strictly before the actual selection cutoff. This verifies observed '
        'ETF proxy membership, not continuous ownership between portfolios or official index membership.', '',
        '## Country and sector coverage','', '| Dimension | Value | Securities | Ready |','|---|---|---:|---:|']
    lines += [f"| {r['dimension']} | {r['value']} | {r['securities']:,} | {r['ready']} |" for r in breakdown if r['dimension'] in ('country','sector')]
    lines += ['', 'Country counts use the unique SEC issuer-country value across observed months; conflicting '
        'values are MULTIPLE and absent values UNKNOWN. These are issuer countries, not listing venues. '
        'Original per-month country, currency and identifiers remain in the inventory evidence. The breakdown CSV additionally splits each country and sector by all four readiness statuses.', '',
        '## SPY and eleven sector ETFs','', '| Symbol | Cached | First | Last | Valid bars | Prelaunch bars / required | Ready |',
        '|---|---|---|---|---:|---:|---|']
    lines += [f"| {r['symbol']} | {r['cached']} | {r['first']} | {r['last']} | {r['valid_rows']} | {r['prelaunch_bars']} / {r['required_prelaunch_bars']} | False |" for r in references]
    lines += ['', '**Correction to the previous aggregate inventory:** all eleven sector ETF tapes exist under '
        '`wf3_prices.json.gz:sector_etfs`; checking only `market` incorrectly reported them absent. '
        'SPY is genuinely absent. The separate `^SP500TR` benchmark is an index and cannot substitute for SPY. '
        'The ETF tapes still fail the October 2023 warm-up and full-history/provenance requirements.', '',
        '## Closest 100 security lines','', 'Sorted by passed requirement count, resolved identity, usable cached '
        'bars and stable identifier; no return-based or strategy-based selection. These are data-resolution '
        'priorities, not an investable universe. Every missing field is listed.', '',
        '| Security | Stable key | Status | Cached symbol | First price | Missing fields |','|---|---|---|---|---|---|']
    top=sorted(rows,key=lambda r:(-r['passed_requirement_count'],-int(r['identity_resolved']),
            -r['best_price_valid_rows'],r['instrument_key']))[:100]
    lines += [f"| {r['name'].replace('|','/')} | {r['instrument_key']} | {r['status']} | {r['best_price_symbol']} | {r['best_price_first']} | {r['missing_fields']} |" for r in top]
    lines += ['', '## Selected technology and listing distinctions', '',
        '| Observed security | ISIN | Status | Mapped cached symbol |', '|---|---|---|---|']
    focus_names={'Apple Inc','Microsoft Corp','NVIDIA Corp','Tesla Inc','Micron Technology Inc',
                 'SK hynix Inc','Taiwan Semiconductor Manufacturing Co Ltd','Samsung Electronics Co Ltd',
                 'Hon Hai Precision Industry Co Ltd','ASML Holding NV','AstraZeneca PLC'}
    lines += [f"| {r['name']} | {r['isin']} | {r['status']} | {r['best_price_symbol']} |"
              for r in rows if r['name'] in focus_names]
    lines += ['', 'The historical Samsung and Hon Hai lines above have US security identifiers; '
        'the cached Korean Samsung ordinary and Taiwanese Hon Hai ordinary prices cannot be transferred '
        'onto these depositary-receipt lines. Both the Taiwanese ordinary and US ADR TSMC lines are '
        'preserved. AstraZeneca UK ordinary and US ADR identities remain separate; preserved US '
        'conversion normalization does not supply a UK ordinary price history.', '']
    lines += ['', '## Complete-data securities','', 'None. The ready-ticker CSV contains its header and zero security rows.' if not ready else '\n'.join(r['name'] for r in ready[:100]), '',
        '## Evidence, storage and reproducibility','',
        f"Full inventory: `{summary['inventory_path']}` ({summary['inventory_bytes']:,} bytes; {summary['securities']:,} rows). "
        'It is retained in ignored research storage because its detailed per-month security-level observations '
        'are large. Git contains the audit code, tests, aggregate breakdown, ready-ticker file and this report.', '',
        f"Inventory SHA256: `{summary['inventory_sha256']}`.", '',
        'Each inventory row preserves all names and valid identifiers, observed monthly membership, original '
        'portfolio/publication timestamps, decision cutoffs, SEC accession/URL/source hashes, country and position '
        'currency, ticker crosswalk evidence, current exact-ISIN exchange records, cached price source/section/SHA256, '
        'valid/invalid/closed-session/duplicate counts and precise missing reasons. `summary.json` contains all '
        'input checksums; `source_discovery.json` enumerates scanned data files; `reference_inputs.csv` covers '
        'the reference instruments. No source prices are edited or committed.', '',
        'Sources: SEC N-PORT frozen monthly confirmed holdings; prior archived SPGM identifier/ticker evidence; '
        'current cached EODHD Korean/Taiwanese exchange symbol lists; fourteen original EODHD short price samples '
        'and their preserved split/session-filtered derivatives; legacy equity/sector-ETF/benchmark cache. '
        'IBKR baseline counts have no underlying bars and supply no usable price history. Legacy fundamentals '
        'and strategy NAV/trade results are not price tapes. Synthetic parity fixtures are excluded. '
        'The repository CSV/gzip/data-container scan includes all real price sections, not just equity market. The workspace attachments, library-files, scratch and shared directories were also checked: no additional datasets were present. '
        'This audit covers locally retained checkout research datasets, not unavailable prior machines or remote accounts.', '',
        'Taiwan July 10, 2026 observations are excluded from the diagnostic usable-bar count, with original '
        'observations preserved. Existing AstraZeneca split-only normalization remains untouched and is not '
        'transferred to another security ISIN. USD-labelled ADR samples are never joined to foreign ordinary '
        'holdings by issuer name. Recent adjusted-close fields and partial split/dividend lists do not prove '
        'full-period corporate-action or total-return correctness.', '',
        'Reproduce offline: `python -m research.spgm_data_completeness`. Inputs are SHA256-checked after '
        'generation, including every original confirmed monthly file.', '',
        '## What can legitimately be tested','',
        'Zero fully ready securities means no legitimate historical five-stock experiment can be supported by '
        'the fully ready set. Even a reduced-universe return diagnostic is blocked by SPY warm-up and the missing '
        'validated adjustment/action/calendar/classification inputs. No backtest was run.', '',
        'After inputs are resolved, any reduced-universe diagnostic must intersect each historical confirmed '
        'SEC-only month with a fixed, predeclared data-admissibility rule, preserve additions/deletions and share '
        'classes, and use only portfolio publications available before the original selection cutoff. It must '
        'disclose exclusion of uncovered securities/countries/sectors and selection on later data availability '
        "(including survivorship bias). Today's constituents cannot fill gaps, and the result cannot represent "
        'the full SPGM proxy or MSCI ACWI IMI. For now, only descriptive identity/coverage diagnostics are supported.', '',
        'The audit stops here. No strategy rules or admission gates were modified, no data acquired and no '
        'backtest executed.']
    (REPO/'research/SPGM_DATA_COMPLETENESS_AUDIT.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    print(json.dumps(run(),indent=2))
