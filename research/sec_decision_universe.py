"""Freeze SEC-only SPGM membership at NY16:20 on actual reference month ends."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from research.spgm_sources import DEFAULT_OUTPUT, ROOT
from research.spgm_proxy import write_csv
from research.spgm_strategy_audit import metrics, audit_queries
from research.spgm_universe import latest_public, evidence_index, construct, company_counts, gzip_csv


def reference_decisions():
    import exchange_calendars as xc
    calendar = xc.get_calendar('XNYS',start='2022-10-01',end='2026-10-05')
    groups = defaultdict(list)
    for stamp in calendar.sessions:
        day = stamp.date()
        if '2022-10-01' <= day.isoformat() <= '2026-09-30':
            groups[day.isoformat()[:7]].append(day)
    result = []
    for month,days in sorted(groups.items()):
        day = max(days)
        cutoff = datetime.combine(day,time(16,20),ZoneInfo('America/New_York')).astimezone(timezone.utc)
        close = calendar.session_close(str(day)).to_pydatetime()
        result.append(dict(selection_month=month,signal_date=day.isoformat(),
            selection_cutoff_utc=cutoff.isoformat(),reference_close_utc=close.isoformat(),
            calendar='XNYS',calendar_library_version=xc.__version__))
    if len(result)!=48:raise ValueError('Expected48 reference decisions')
    return result


def classify_status(row):
    if row['eligibility']=='eligible':return 'CONFIRMED'
    if row['eligibility']=='provisional':return 'PROVISIONAL'
    if row.get('asset_category')=='EC' and ('identifier' in row.get('eligibility_reason','') or 'ambiguous' in row.get('eligibility_reason','')):
        return 'UNRESOLVED'
    return 'INELIGIBLE'


def freeze(output=DEFAULT_OUTPUT):
    output = Path(output).resolve()
    if ROOT.resolve() not in output.parents:raise ValueError('Ignored output required')
    snapshots = json.loads((output/'snapshots.json').read_text())
    groups = defaultdict(list)
    for r in csv.DictReader((output/'holdings.csv').open()):groups[r['snapshot_id']].append(r)
    if len(snapshots)!=21:raise ValueError('Expected21 original portfolios')
    for s in snapshots:
        if len(groups[s['snapshot_id']])!=s['holdings_count']:raise ValueError('Position count mismatch')
    out = output/'sec_only_decision_universe'
    out.mkdir(exist_ok=True)
    summaries,countries,companies,statuses,hashes = [],[],[],[],{}
    for decision in reference_decisions():
        cutoff = decision['selection_cutoff_utc']
        selected = latest_public(snapshots,cutoff,sec_only=True)
        if selected is None:raise ValueError('No prior-public SEC portfolio')
        eligible,provisional,excluded = construct(selected,groups,evidence_index(snapshots,groups,cutoff),cutoff)
        if any(datetime.fromisoformat(r['available_at'])>=datetime.fromisoformat(cutoff) for r in eligible):
            raise ValueError('Look-ahead evidence')
        for row in eligible+provisional+excluded:
            row.update(dataset_label='SPGM HISTORICAL ETF HOLDINGS PROXY',
                membership_status=classify_status(row),
                strategy_input_status='UNRESOLVED' if not row.get('sector') or not row.get('exchange_mic') else 'PROVISIONAL',
                source_url=selected['source_url'],source_filing=selected['snapshot_id'])
        count = Counter(r['country'] or 'UNKNOWN' for r in eligible)
        summary = {**decision,**metrics(eligible,cutoff),**company_counts(eligible),
            'source_snapshot_id':selected['snapshot_id'],'source_portfolio_date':selected['portfolio_date'],
            'source_publication_date':selected['publication_date'],'source_available_at':selected['available_at'],
            'source_url':selected['source_url'],'source_sha256':selected['sha256'],
            'portfolio_age_days':(datetime.fromisoformat(cutoff).date()-datetime.fromisoformat(selected['portfolio_date']).date()).days,
            'membership_confirmed':len(eligible),'membership_provisional':len(provisional),
            'membership_unresolved':sum(classify_status(r)=='UNRESOLVED' for r in excluded),
            'membership_ineligible':sum(classify_status(r)=='INELIGIBLE' for r in excluded),
            'country_distribution_json':json.dumps(dict(sorted(count.items()))),
            'in_backtest_selection_window':'2023-10'<=decision['selection_month']<='2026-09',
            'prelaunch_signal':decision['selection_month']=='2023-09'}
        summaries.append(summary)
        for country,n in sorted(count.items()):
            subset = [r for r in eligible if (r['country'] or 'UNKNOWN')==country]
            countries.append({'month':decision['selection_month'],'country':country,**metrics(subset,cutoff)})
        # No verified sector assignment exists; preserve UNKNOWN as audit label
        # only. It is never sent to strategy concentration/regime functions.
        statuses.append({'month':decision['selection_month'],'sector':'UNRESOLVED',
                         'eligible_securities':len(eligible),'historical_gics_verified':summary['historical_gics_verified']})
        queried = defaultdict(list)
        for row in eligible:
            for company in audit_queries(row):queried[company].append(row)
        for company,rows in queried.items():
            companies.append({'month':decision['selection_month'],'company':company,**metrics(rows,cutoff)})
        for suffix,rows in (('confirmed',eligible),('other_membership_status',provisional+excluded)):
            path = out/(decision['selection_month']+'_'+suffix+'.csv.gz')
            gzip_csv(path,rows);hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    write_csv(out/'monthly_summary.csv',summaries)
    write_csv(out/'country_completeness.csv',countries)
    write_csv(out/'sector_completeness.csv',statuses)
    write_csv(out/'priority_company_completeness.csv',companies)
    manifest = dict(dataset_label='SPGM HISTORICAL ETF HOLDINGS PROXY',policy='SEC-only latest prior-public portfolio',
        metadata_policy='Original source plus exact-ID joins only to information public before the cutoff; archives can supply prior-known metadata, not membership',
        cutoff_policy='Actual XNYS month-end session at16:20 America/New_York, including early-close days; original trial publication buffer retained',
        months=48,backtest_month_ends=36,prelaunch_signal='2023-09-29',
        historical_gics_verified=sum(s['historical_gics_verified'] for s in summaries),
        verified_listing=sum(s['verified_listing'] for s in summaries),
        security_months=sum(s['securities'] for s in summaries),
        input_snapshots_sha256=hashlib.sha256((output/'snapshots.json').read_bytes()).hexdigest(),
        input_holdings_sha256=hashlib.sha256((output/'holdings.csv').read_bytes()).hexdigest(),
        output_sha256=hashes,eodhd_requests=0)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'monthly_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    lines=['# Frozen SEC-only decision universe','',
        '**SPGM HISTORICAL ETF HOLDINGS PROXY — not official MSCI ACWI IMI constituents.**','',
        '48 reference month ends rebuilt offline at NY16:20 on actual XNYS sessions.36 month ends fall in October2023–September2026; September29 2023 supplies the initial prelaunch signal for the first October opening. The original48 latest-source/midnight universes remain unchanged. Publication and acceptance dates are preserved, never replaced with portfolio dates.','',
        'SEC-only refers to membership. Older prior-public exact-ID publisher ticker observations may enrich SEC records. All such ticker observations remain venue-unverified. CONFIRMED is a common-equity membership status; the separate strategy-input status is UNRESOLVED until sector/listing/price/FX gates pass. INELIGIBLE and missing-ID UNRESOLVED observations remain in separate evidence exports. No present-day list or guessed sector is used.','',
        '| Month | Signal date | Cutoff UTC | Portfolio | Public date | Age | Confirmed | Ticker observed | LEI gaps | GICS | Verified listing | Membership unresolved |',
        '|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"| {r['selection_month']} | {r['signal_date']} | {r['selection_cutoff_utc']} | {r['source_portfolio_date']} | {r['source_publication_date']} | {r['portfolio_age_days']} | {r['securities']} | {r['ticker_observed']} | {r['missing_verified_issuer_lei']} | {r['historical_gics_verified']} | {r['verified_listing']} | {r['membership_unresolved']} |")
    total=manifest['security_months']
    lines += ['',f"Totals: **{total:,}** confirmed security-months; prior-public ticker observations **{sum(s['ticker_observed'] for s in summaries):,}**; valid source LEI gaps **{sum(s['missing_verified_issuer_lei'] for s in summaries):,}**. Historical GICS and verified listing coverage remain **0%**. Confirmed equities range **{min(s['securities'] for s in summaries):,}–{max(s['securities'] for s in summaries):,}**, age **{min(s['portfolio_age_days'] for s in summaries)}–{max(s['portfolio_age_days'] for s in summaries)} days**.", '',
        'Country, sector-gap and priority-company matrices and all source-backed compressed evidence are stored under ignored `research/eodhd_output/spgm_proxy/sec_only_decision_universe/`. Sector UNKNOWN is an audit gap, not an approximation supplied to the strategy. The calendar version and early-close timestamps are retained per decision.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return manifest


if __name__=='__main__':
    result=freeze();print(json.dumps({k:v for k,v in result.items() if k!='output_sha256'}))
