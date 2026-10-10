"""Audit sourced sector overlays against all frozen SEC-only security rows."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from research.classification_policy import MODES,coverage
from research.spgm_sources import DEFAULT_OUTPUT,ROOT


def run(records_path=None):
    frozen=DEFAULT_OUTPUT/'sec_only_decision_universe'
    manifest=json.loads((frozen/'manifest.json').read_text())
    overlays={}
    if records_path:
        records_path=Path(records_path).resolve()
        if ROOT.resolve() not in records_path.parents:raise ValueError('Sector overlays must stay ignored')
        for record in json.loads(records_path.read_text()):
            key=record['instrument_key']
            if key in overlays:raise ValueError('Duplicate sector overlay security')
            # Verify evidence hashes here as well as in executable bundles.
            for source in ([record['current_gics']] if record.get('current_gics') else [])+record.get('historical_gics_corrections',[]):
                path=(records_path.parent/source['evidence_file']).resolve()
                if ROOT.resolve() not in path.parents:raise ValueError('Classification source must stay ignored')
                if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Classification source checksum mismatch')
            overlays[key]=record
    snapshots=[]
    for month in json.loads((frozen/'monthly_summary.json').read_text()):
        filename=month['selection_month']+'_confirmed.csv.gz'
        path=frozen/filename
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['output_sha256'][filename]:raise ValueError('Frozen universe changed')
        with gzip.open(path,'rt') as stream:members=list(csv.DictReader(stream))
        rows=[]
        for member in members:
            overlay=overlays.get(member['instrument_key'],{})
            # Sector-only overlay cannot change historical membership/listing fields.
            rows.append(member|{k:v for k,v in overlay.items() if k in {'current_gics','historical_gics_corrections'}})
        snapshots.append(dict(decision_at=month['selection_cutoff_utc'],members=rows))
    out=DEFAULT_OUTPUT/'historical_backtest/classification_audit'
    out.mkdir(parents=True,exist_ok=True)
    reports={mode:coverage(snapshots,mode) for mode in MODES}
    for mode,report in reports.items():
        report['source_overlay_sha256']=hashlib.sha256(records_path.read_bytes()).hexdigest() if records_path else None
        report['source_policy']='exact instrument-key joins; original membership preserved'
        (out/(mode+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    lines=['# Sector admission coverage audit','','No current labels are promoted to historical verification.','',
           '| Mode | Security-months | Covered | Approximated | Minimum gate |','|---|---:|---:|---:|---|']
    for mode,report in reports.items():
        rows=report['snapshots']
        lines.append(f"| {mode} | {sum(r['securities'] for r in rows)} | {sum(r.get('covered',0) for r in rows)} | {sum(r.get('approximate',0) for r in rows)} | {report['minimum_coverage_pass']} |")
    lines+=['','Country/sector denominators, each unresolved security and reasons are recorded in ignored JSON. Performance/ranking sensitivity remains null until complete validated price histories exist. The original503 undated staged sector labels are not a sourced, identity-matched GICS overlay.']
    (out/'coverage.md').write_text('\n'.join(lines)+'\n')
    return reports


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path)
    result=run(parser.parse_args().records)
    print(json.dumps({mode:dict(minimum_coverage_pass=r['minimum_coverage_pass'],
        security_months=sum(m['securities'] for m in r['snapshots']),
        covered=sum(m.get('covered',0) for m in r['snapshots']),
        approximate=sum(m.get('approximate',0) for m in r['snapshots'])) for mode,r in result.items()}))
