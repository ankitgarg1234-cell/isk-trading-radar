"""WBD pre-delisting alternate-source price recovery (one-shot, no API keys).

Yahoo's current bulk endpoint shows missing WBD after its corporate event,
so recovery must confirm >=127 completed NYSE sessions to September 30
using independently source-attributed pre-delisting daily prices. This is
only a diagnostic: NO ranking/price/corporate-action certification.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import StringIO
import csv
import json

from gem_data.gem_nyse_2026_manifest import published_schedule_2026


def examine_wbd_daily_prices(*, get=None, yahoo_ticker_factory=None):
    required=[row["session"] for row in published_schedule_2026()["sessions"]
              if row["session"]<="2026-09-30"][-127:]
    if get is None:
        import requests
        get=requests.get
    out={"schema":"gem-wbd-pre-delisting-source-diagnostic-v1",
         "symbol":"WBD","cik":"0001437107","as_of":"2026-09-30",
         "sources":[],"qualified_for_final_ranking":False,
         "corporate_actions_certified":False,"source_certified":False,
         "trading_authorized":False}
    url="https://stooq.com/q/d/l/?s=wbd.us&i=d&d1=20260301&d2=20260930"
    try:
        res=get(url,timeout=15)
        res.raise_for_status()
        content=res.content
        if len(content)>2000000:
            raise ValueError("Source response oversized")
        rows=list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
        mapping={}
        for row in rows:
            day=row.get("Date","")
            if day in mapping:
                raise ValueError("Duplicate date")
            if day and day<="2026-09-30":
                mapping[day]=row
        has_all=all(day in mapping for day in required)
        data=[mapping[day] for day in required if day in mapping]
        has_fields=has_all and all(
            float(row.get("Close",0))>0 and float(row.get("Volume",0))>=0
            for row in data)
        out["sources"].append({
            "provider":"STOOQ_PUBLIC_CSV",
            "http_sha256":sha256(content).hexdigest(),
            "historical_rows":len(rows),
            "requested_NYSE_sessions":127,
            "matching_sessions":len(data),
            "complete_127_session_window":bool(has_fields),
            "source_adjustment_method_verified":False,
            "last_pre_delist_close":float(mapping["2026-09-30"]["Close"])
                if "2026-09-30" in mapping else None,
        })
    except Exception as exc:
        out["sources"].append({
            "provider":"STOOQ_PUBLIC_CSV","state":"UNAVAILABLE",
            "error_type":type(exc).__name__})
    try:
        if yahoo_ticker_factory is None:
            import yfinance as yf
            yahoo_ticker_factory=yf.Ticker
        frame=yahoo_ticker_factory("WBD").history(
            start="2026-03-01",end="2026-10-01",
            auto_adjust=False,actions=True,repair=False)
        rows={}
        if frame is not None and not frame.empty:
            for idx, r in frame.iterrows():
                stamp=idx.strftime("%Y-%m-%d")
                rows[stamp]=r
        matched=[day for day in required if day in rows]
        out["sources"].append({
            "provider":"YFINANCE_PRE_DELISTING_HISTORICAL_ENDPOINT",
            "matching_sessions":len(matched),
            "complete_127_session_window":len(matched)==127,
            "source_adjustment_method_verified":False,
        })
    except Exception as exc:
        out["sources"].append({
            "provider":"YFINANCE_PRE_DELISTING_HISTORICAL_ENDPOINT",
            "state":"UNAVAILABLE","error_type":type(exc).__name__})
    return out
