"""Extract original inline-XBRL facts; no companyfacts backfill or revised vintages.

This is staging, not universal accounting certification. Dimensional facts remain
visible and are excluded from downstream default metrics. lxml is required.
"""
import csv, gzip, json, pathlib
from decimal import Decimal, InvalidOperation
from lxml import html

ROOT=pathlib.Path(__file__).resolve().parent

def local(tag):
    return tag.rsplit('}',1)[-1].split(':')[-1].lower() if isinstance(tag,str) else ''

def extract(path, source_id):
    tree=html.fromstring(gzip.open(path,'rb').read())
    contexts={}
    for e in tree.iter():
        if local(e.tag) != 'context':continue
        d={'context_id':e.get('id'), 'dimensions':[]}
        for n in e.iter():
            tag=local(n.tag);v=''.join(n.itertext()).strip()
            if tag in ['startdate','enddate','instant']:d[tag]=v
            if tag in ['explicitmember','typedmember']:d['dimensions'].append(v)
        contexts[d['context_id']]=d
    for e in tree.iter():
        if local(e.tag) != 'nonfraction':continue
        name=e.get('name','');ctx=e.get('contextref','')
        raw=''.join(e.itertext()).replace('\xa0',' ').strip()
        row=dict(source_id=source_id,concept=name,context_id=ctx,unit_ref=e.get('unitref'),scale=e.get('scale','0'),sign=e.get('sign',''),displayed=raw,decimals=e.get('decimals'),**{k:contexts.get(ctx,{}).get(k) for k in ['startdate','enddate','instant']})
        row['dimensions']='|'.join(contexts.get(ctx,{}).get('dimensions',[]));row['has_dimensions']=bool(row['dimensions'])
        try:
            s=raw.replace(',','').replace('$','').replace(' ','').replace('(','-').replace(')','')
            if s in ['—','-','–']:s='0'
            v=Decimal(s)*(Decimal(10)**int(row['scale']))
            if row['sign']=='-':v=-abs(v)
            row['value']=str(v);row['status']='extracted'
        except (InvalidOperation,ValueError):row['value']='';row['status']='unparsed'
        yield row

def main():
    manifest=json.loads((ROOT/'download_manifest.json').read_text());rows=[]
    seen=set()
    for r in manifest:
        if r['status']!='downloaded' or r['source_id'] in seen:continue
        seen.add(r['source_id'])
        p=ROOT/r['local_path']
        if p.suffixes[-2:]!=['.bin','.gz']:continue
        for row in extract(p,r['source_id']):
            row.update(ticker=r['ticker'],publication_date=r['publication_date'],raw_sha256=r['raw_sha256'],source_url=r['url']);rows.append(row)
    if rows:
        with (ROOT/'original_inline_facts.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({'original_sources':len(seen),'inline_facts':len(rows),'unparsed':sum(r['status']=='unparsed' for r in rows),'dimensioned':sum(r['has_dimensions'] for r in rows)}))

if __name__=='__main__':main()
