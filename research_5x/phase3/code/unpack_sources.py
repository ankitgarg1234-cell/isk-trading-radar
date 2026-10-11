"""Restore preserved source bytes without overwriting changed local files."""
from pathlib import Path
import hashlib,json,zipfile
OUT=Path(__file__).resolve().parents[1]
def main():
    m=json.loads((OUT/'source_bundles/manifest.json').read_text());count=0
    for b in m['bundles']:
        p=OUT/b['path']
        if hashlib.sha256(p.read_bytes()).hexdigest()!=b['sha256']:raise ValueError('Source bundle hash mismatch: '+str(p))
        with zipfile.ZipFile(p) as z:
            for e in b['members']:
                target=(OUT/e['path']).resolve()
                if not target.is_relative_to(OUT):raise ValueError('Unsafe archive path')
                raw=z.read(e['path'])
                if hashlib.sha256(raw).hexdigest()!=e['sha256']:raise ValueError('Member hash mismatch')
                if target.exists():
                    if hashlib.sha256(target.read_bytes()).hexdigest()!=e['sha256']:raise ValueError('Changed local file; refusing overwrite: '+str(target))
                else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                count+=1
    print('Verified/restored',count,'source/intermediate files; no changed file overwritten.')
if __name__=='__main__':main()
