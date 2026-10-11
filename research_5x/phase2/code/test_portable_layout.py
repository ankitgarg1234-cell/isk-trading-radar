"""Stage exact public files in an isolated repository layout and run offline checks."""
from phase2_bootstrap import ROOT,OUT,e
from pathlib import Path
import tempfile,shutil,json,subprocess,sys

def main():
    manifest=json.loads((OUT/'publication_manifest.json').read_text());dest=Path(tempfile.mkdtemp(prefix='phase2-repro-'))
    for rec in manifest['files']:
        source=ROOT/rec['path'];target=dest/rec['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name in manifest['repository_inputs_already_in_base']:
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(e.REPO/name,target)
    checks=[]
    for script in ['replay_published_winner.py','verify_phase2.py','analyze_acceleration.py','quarter_observables.py']:
        result=subprocess.run([sys.executable,str(dest/'research_5x/phase2/code'/script)],cwd=dest,text=True,capture_output=True,timeout=120)
        checks.append({'script':script,'exit_code':result.returncode,'stdout':result.stdout[-2000:],'stderr':result.stderr[-1000:]})
        if result.returncode:break
    # Generated outputs must agree with workspace report inputs.
    names=['panel/screen_results.csv','panel/continuous_correlations.csv','panel/released_quarter_observables.csv']
    comparisons=[]
    for name in names:
        f=dest/'research_5x/phase2/2026-10-11_earnings_acceleration'/name
        comparisons.append({'file':name,'sha256':e.sha(f) if f.exists() else None,'matches':f.exists() and e.sha(f)==e.sha(OUT/name)})
    result={'pass':all(x['exit_code']==0 for x in checks) and all(x['matches'] for x in comparisons),'checks':checks,'comparisons':comparisons,
      'layout':'Newrepositoryroot with onlypublicationfiles and3frozenbaseinputs; no research_repository subfolder orOctober11ZIP',
      'artifact_privacy':'Temporarylocalpaths omitted fromsavedreport'}
    e.dump(OUT/'portable_layout_test.json',result);shutil.rmtree(dest);print(json.dumps(result,indent=2))
    if not result['pass']:raise SystemExit(1)
if __name__=='__main__':main()
