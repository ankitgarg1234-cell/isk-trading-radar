from datetime import datetime, timezone


def history(start=60.0, days=260, daily=0.25, last_volume_multiplier=2.2):
    rows=[]
    for i in range(days):
        close=start+i*daily
        rows.append({"date":f"2026-01-{(i%28)+1:02d}","open":close-.4,"high":close+1.0,"low":close-1.0,"close":close,"volume":1_000_000})
    rows[-1]["volume"] = int(rows[-1]["volume"]*last_volume_multiplier)
    return rows


def strong_fundamentals():
    return {
        "marketCap":2_000_000_000,"floatShares":50_000_000,
        "revenueGrowth":.30,"quarterlyRevenueGrowth":.28,"earningsGrowth":.35,"grossMargins":.65,"operatingMargins":.24,
        "returnOnEquity":.28,"debtToEquity":35,"forwardPE":28,
        "targetMeanPrice":150,"targetHighPrice":175,"targetLowPrice":105,
        "recommendationMean":1.7,"sector":"Technology"
    }


def positive_news():
    now=int(datetime.now(timezone.utc).timestamp())
    return [
        {"title":"Company raises guidance after record earnings beat","publisher":"Reuters","published":now,"link":"https://example.com/a"},
        {"title":"Company wins major contract and announces partnership","publisher":"Business Wire","published":now,"link":"https://example.com/b"},
    ]


def negative_news(two=True):
    now=int(datetime.now(timezone.utc).timestamp())
    rows=[{"title":"Company cuts guidance after earnings miss","publisher":"Reuters","published":now,"link":"https://example.com/c"}]
    if two: rows.append({"title":"SEC investigation follows accounting warning","publisher":"Bloomberg","published":now,"link":"https://example.com/d"})
    return rows


def bundle(fundamentals=None, news=None, price=124.75):
    return {
        "symbol":"TEST","price":price,"previous_close":123.0,"currency":"USD","exchange":"NMS",
        "history":history(),"fundamentals":fundamentals if fundamentals is not None else strong_fundamentals(),
        "news":news if news is not None else positive_news(),
        "corporate_actions":{"splits_1y":[],"recent_reverse_split":False},
        "strategic_capital":{"direction":"NONE","evidence_strength":0,"events":[]},
        "sector_benchmark":{"symbol":"XLK","price":250,"history":history(start=180,daily=.28,last_volume_multiplier=1.1)},
        "provider":"fake","asof":"2026-09-27T12:00:00+00:00"
    }
