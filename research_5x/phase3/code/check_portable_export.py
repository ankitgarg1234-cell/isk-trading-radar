"""Check offline reproduction using only manifest files and the preserved parent.

Pass a clean checkout of the declared parent as the destination. No retrieval,
strategy evaluation, trading, or production writes occur.
"""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    dest=Path(sys.argv[1]).resolve()
    if not (dest/'.git').exists():raise ValueError('Destination must be a parent checkout')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dest,text=True).strip()
    manifest=json.loads((OUT/'publication_manifest.json').read_text())
    input_sha=digest(OUT/'publication_manifest.json')
    archived=OUT/'validation/portable_inputs'/f'{input_sha}.json'
    archived.parent.mkdir(parents=True,exist_ok=True)
    archived.write_bytes((OUT/'publication_manifest.json').read_bytes())
    if head!=manifest['parent_sha']:raise ValueError('Unexpected parent commit')
    if (dest/'research_5x/phase3').exists():raise ValueError('Use a fresh destination without Phase3')
    for x in manifest['files']:
        src=ROOT/x['path'];target=dest/x['path']
        if digest(src)!=x['sha256']:raise ValueError('Stale manifest: '+x['path'])
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(src.read_bytes())
    target=dest/'research_5x/phase3/publication_manifest.json'
    target.write_bytes((OUT/'publication_manifest.json').read_bytes())
    scripts=['unpack_sources.py','build_cohorts.py','stage_accounting.py','cohort_uncertainty.py','build_phase3.py','verify_phase3.py']
    runs=[]
    for name in scripts:
        p=dest/'research_5x/phase3/code'/name
        r=subprocess.run([sys.executable,str(p)],cwd=dest,capture_output=True,text=True,env=os.environ.copy())
        runs.append({'script':name,'exit_code':r.returncode,'output':r.stdout+r.stderr})
        if r.returncode:raise RuntimeError(runs[-1])
    # Compare every generated core cohort/staging/summary output, including figures.
    checks=[]
    for x in manifest['files']:
        rel=Path(x['path']).relative_to('research_5x/phase3')
        core=(rel.parts[0]=='figures' or rel==Path('research_report.html') or rel==Path('retention/prior_evidence_references.csv') or (rel.parts[0]=='accounting_quality' and len(rel.parts)==2 and rel.suffix in ['.csv','.gz','.json']))
        if core:
            actual=digest(dest/x['path']);checks.append({'path':x['path'],'expected_sha256':x['sha256'],'reproduced_sha256':actual,'pass':actual==x['sha256']})
    verification=json.loads((dest/'research_5x/phase3/validation/verification.json').read_text())
    record={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'parent_sha':head,'input_export_manifest_sha256':input_sha,'input_export_manifest_path':str(archived.relative_to(OUT)),'network_retrieval_used':False,'scripts':runs,'deterministic_output_checks':checks,'all_outputs_identical':all(x['pass'] for x in checks),'all_test_suites_pass':verification['all_test_suites_pass'],'phase2_preserved':verification['phase2_preserved'],'interpretation':'Portable data/arithmetic reproduction, not independent financial outcome validation.'}
    (OUT/'validation/portable_reproduction.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k not in ['scripts','deterministic_output_checks']},indent=2))
    print('Compared',len(checks),'core outputs')
    if not record['all_outputs_identical']:raise SystemExit(1)

if __name__=='__main__':main()
