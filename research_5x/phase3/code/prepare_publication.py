"""Bundle source retention and list only research files for publication."""
from pathlib import Path
import hashlib,json,zipfile,zlib
OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]
def main():
    raw=[]
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts:continue
        if 'raw' in p.relative_to(OUT).parts or p.name in ['original_inline_facts.csv','original_inline_xbrl_facts.csv']:
            raw.append(p)
    groups=[];g=[];size=0
    for p in raw:
        estimate=len(zlib.compress(p.read_bytes(),9))+200
        if g and size+estimate>2500000:groups.append(g);g=[];size=0
        g.append(p);size+=estimate
    if g:groups.append(g)
    folder=OUT/'source_bundles';folder.mkdir(exist_ok=True);bundles=[]
    for i,files in enumerate(groups,1):
        zpath=folder/f'preserved_sources_{i:02d}.zip';members=[]
        with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for p in files:
                name=str(p.relative_to(OUT));data=p.read_bytes();info=zipfile.ZipInfo(name,date_time=(2026,10,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data,compresslevel=9)
                members.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        bundles.append({'path':str(zpath.relative_to(OUT)),'bytes':zpath.stat().st_size,'sha256':hashlib.sha256(zpath.read_bytes()).hexdigest(),'members':members})
    (folder/'manifest.json').write_text(json.dumps({'purpose':'Exact source/intermediate byte preservation; run code/unpack_sources.py before reproduction. No changed file overwritten.','bundles':bundles},indent=2)+'\n')
    bundled=set(raw);public=[]
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or p in bundled or '__pycache__' in p.parts or p.name in ['publication_manifest.json','publication_receipt.json']:continue
        if p.name.endswith('.zip') and p.parent!=folder:continue
        data=p.read_bytes();public.append({'path':str(p.relative_to(ROOT)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'git_blob_sha':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()})
    (OUT/'publication_manifest.json').write_text(json.dumps({'branch':'research/phase3-accounting-quality-validation','parent_sha':'4ea44011e3911227f9be2266d5dcb6c078b8722a','base_tree_sha':'062c5ff08998c9cb039a08d27a8cebda0e564b7d','files':public},indent=2)+'\n')
    print({'public_files_excluding_manifest':len(public),'public_bytes':sum(x['bytes'] for x in public),'bundled_original_files':len(raw),'bundles':len(bundles)})
if __name__=='__main__':main()
