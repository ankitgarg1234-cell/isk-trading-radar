"""Sequential acquisition with cache-first resumption and fail-closed quotas.

No network action on import or by default. A caller must supply a verified
entitlement and mappings; unknown or stale quota reports cannot authorize costs.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

from research.eodhd_client import ENDPOINT_COSTS,ResearchClient
from research.spgm_sources import ROOT


class ResumableAcquisition:
    def __init__(self,output,*,quota,history_entitled,max_units,client=None):
        self.output=Path(output).resolve()
        if ROOT.resolve() not in self.output.parents:raise ValueError('Ignored acquisition output required')
        self.output.mkdir(parents=True,exist_ok=True)
        self.quota=quota
        self.history_entitled=history_entitled
        self.max_units=max_units
        self.client=client or ResearchClient(self.output/'request_cost_ledger.json',budget=max_units,request_limit=20)
        self.path=self.output/'acquisition_manifest.json'
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {}
        if max_units<0:raise ValueError('Invalid budget')

    def get(self,endpoint,symbol,*,mapping_verified,**params):
        key=hashlib.sha256(json.dumps([endpoint,symbol,params],sort_keys=True).encode()).hexdigest()
        target=self.output/(key+'.json')
        existing=self.state.get(key)
        if existing and existing['status']=='ok' and target.exists():
            body=target.read_bytes()
            if hashlib.sha256(body).hexdigest()!=existing['sha256']:raise ValueError('Cache checksum mismatch')
            return json.loads(body)
        if existing:raise RuntimeError('Previous request failed; explicit reviewed retry required')
        if endpoint not in {'eod','splits'} or not mapping_verified or not self.history_entitled:
            raise RuntimeError('Verified mapping and historical entitlement required')
        today=datetime.now(timezone.utc).date().isoformat()
        if not self.quota.get('quota_date_is_current') or self.quota.get('api_requests_date')!=today:
            raise RuntimeError('Stale quota response; do not assume a midnight reset')
        spent=sum(r['cost'] for r in self.state.values())
        cost=ENDPOINT_COSTS[endpoint]
        allowance=self.quota.get('reported_remaining_units',0)
        if spent+cost>min(self.max_units,allowance):raise RuntimeError('Quota/budget exhausted')
        # Reserve before sending; failed attempts retain their cost. No hidden
        # retries, redirects, parallel requests or live execution.
        self.state[key]={'status':'reserved','cost':cost,'endpoint':endpoint,'symbol':symbol}
        self.path.write_text(json.dumps(self.state,indent=2)+'\n')
        try:
            payload=self.client.get(endpoint,symbol,**params)
            body=(json.dumps(payload,sort_keys=True)+'\n').encode()
            target.write_bytes(body)
            self.state[key].update(status='ok',sha256=hashlib.sha256(body).hexdigest())
        except Exception:
            self.state[key]['status']='failed'
            raise
        finally:self.path.write_text(json.dumps(self.state,indent=2)+'\n')
        return payload
