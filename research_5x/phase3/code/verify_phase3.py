"""Offline verification entry point; no data retrieval or trades."""
from pathlib import Path
import hashlib,json,subprocess,sys,datetime
OUT=Path(__file__).resolve().parents[1]
def main():
    suites=[OUT/'code/test_phase3.py',OUT/'accounting_quality/issuer_audits/failures/test_failure_audits.py',OUT/'accounting_quality/issuer_audits/matched_peers/test_case_audit.py']
    runs=[]
    for p in suites:
        if not p.exists():raise FileNotFoundError(p)
        r=subprocess.run([sys.executable,str(p)],cwd=p.parent,capture_output=True,text=True)
        runs.append({'suite':str(p.relative_to(OUT)),'exit_code':r.returncode,'output':r.stdout+r.stderr})
    prior=json.load(open(OUT/'validation/phase2_preservation.json'))
    root=OUT.parents[1];source_files=[]
    for x in prior['files']:
        p=root/x['path'];source_files.append({'path':x['path'],'expected':x['expected'],'actual':hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None,'pass':p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==x['expected']})
    outputs={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'suite_results':runs,'all_test_suites_pass':all(x['exit_code']==0 for x in runs),'phase2_readonly_hash_checks':len(source_files),'phase2_preserved':all(x['pass'] for x in source_files),'phase2_checks':source_files,'checks_scope':'Regression/data-integrity checks only, not predictive or independent-cycle validation.'}
    (OUT/'validation/verification.json').write_text(json.dumps(outputs,indent=2)+'\n')
    print(json.dumps({k:v for k,v in outputs.items() if k not in ['suite_results','phase2_checks']},indent=2))
    for r in runs:print(r['suite'],r['output'].strip())
    if not outputs['all_test_suites_pass'] or not outputs['phase2_preserved']:raise SystemExit(1)
if __name__=='__main__':main()
