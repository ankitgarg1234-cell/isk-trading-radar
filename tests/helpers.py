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
        "revenueGrowth":.30,"earningsGrowth":.35,"grossMargins":.65,"operatingMargins":.24,
        "returnOnEquity":.28,"debtToEquity":35,"forwardPE":28,
        "targetMeanPrice":150,"targetHighPrice":175,"targetLowPrice":105,
        "recommendationMean":1.7,"sector":"Technology","marketCap":5_000_000_000
    }


def positive_news():
    now=int(datetime.now(timezone.utc).timestamp())
    return [
        {"title":"Company raises guidance after record earnings beat","publisher":"Reuters","relatedTickers":["TEST"],"published":now,"link":"https://example.com/a"},
        {"title":"Company wins major contract and announces partnership","publisher":"Business Wire","relatedTickers":["TEST"],"published":now,"link":"https://example.com/b"},
    ]


def negative_news(two=True):
    now=int(datetime.now(timezone.utc).timestamp())
    rows=[{"title":"Company cuts guidance after earnings miss","publisher":"Reuters","relatedTickers":["TEST"],"published":now,"link":"https://example.com/c"}]
    if two: rows.append({"title":"SEC investigation follows accounting warning","publisher":"Bloomberg","relatedTickers":["TEST"],"published":now,"link":"https://example.com/d"})
    return rows


def bundle(fundamentals=None, news=None, price=124.75):
    return {
        "symbol":"TEST","price":price,"previous_close":123.0,"currency":"USD","exchange":"NMS",
        "history":history(),"fundamentals":fundamentals if fundamentals is not None else strong_fundamentals(),
        "news":news if news is not None else positive_news(),
        "sector_benchmark":{"symbol":"XLK","price":250,"history":history(start=180,daily=.28,last_volume_multiplier=1.1)},
        "provider":"fake","asof":datetime.now(timezone.utc).isoformat()
    }
