"""Secondary public price recovery attempts, never injected on ambiguous identity."""
import urllib.request,urllib.parse,json,time
from pathlib import Path
from datetime import datetime,timezone
O=Path(__file__).resolve().parent;out=[]
for s in ['ANSS','CTRA','DAY','DFS','HES','HOLX','IPG','JNPR','K','WBA']:
 url='https://stooq.com/q/d/l/?'+urllib.parse.urlencode({'s':s.lower()+'.us','d1':'20240101','d2':'20261009','i':'d'})
 try:
  with urllib.request.urlopen(url,timeout=15) as resp:raw=resp.read();status=resp.status
  text=raw.decode(errors='replace');valid=text.startswith('Date,Open,High,Low,Close,Volume');out.append({'ticker':s,'url':url,'http_status':status,'bytes':len(raw),'retrieved_at':datetime.now(timezone.utc).isoformat(),'result':'UNVERIFIED_CSV_IDENTITY_AND_ACTIONS' if valid else 'NO_USABLE_HISTORY','response_excerpt':text[:120]})
 except Exception as ex:out.append({'ticker':s,'url':url,'result':'REQUEST_FAILED','error':str(ex)})
 time.sleep(.3)
(O/'delisted_public_probe.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
