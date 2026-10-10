"""Parse ECB daily reference observations without inventing publication times.

These are reference-rate candidates, never an automatically admitted opening
FX tape. Network retrieval/terms verification is a separate explicit step.
"""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import date


def derive_usd_reference(csv_text,source):
    rows=list(csv.DictReader(io.StringIO(csv_text)))
    if rows and not {'TIME_PERIOD','CURRENCY','CURRENCY_DENOM','OBS_VALUE'}<=rows[0].keys():
        raise ValueError('Unexpected ECB SDMX CSV schema')
    daily=defaultdict(dict)
    for r in rows:
        if r['CURRENCY_DENOM']!='EUR':raise ValueError('Expected currency units per EUR')
        day=date.fromisoformat(r['TIME_PERIOD']).isoformat()
        try:value=float(r['OBS_VALUE'])
        except (ValueError,TypeError):continue
        if not math.isfinite(value) or value<=0:raise ValueError('Invalid FX observation')
        currency=r['CURRENCY']
        if currency in daily[day] and daily[day][currency]!=value:
            raise ValueError('Conflicting FX revision; choose a verified source vintage')
        daily[day][currency]=value
    derived,missing=[],[]
    for day,rates in sorted(daily.items()):
        if 'USD' not in rates:
            missing.append(dict(date=day,reason='same-date USD/EUR observation absent'))
            continue
        # EUR/EUR=1 is a quote definition, not an invented market observation.
        for currency,units_per_eur in sorted(dict(EUR=1.,**rates).items()):
            derived.append(dict(reference_date=day,currency=currency,
                usd_per_unit=rates['USD']/units_per_eur,
                quote='USD per major currency unit',source=source,
                source_quote='currency units per EUR; synchronous USD/EUR cross',
                publication_at=None,verification='HISTORICAL_REFERENCE_OBSERVATION; RELEASE_TIMING_UNVERIFIED',
                admitted_for_execution=False))
    return derived,missing
