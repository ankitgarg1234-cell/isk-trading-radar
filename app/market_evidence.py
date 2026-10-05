"""Bounded, provenance-preserving helpers for optional market evidence."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import OrderedDict, deque
from threading import Lock
import math
import time

NY = ZoneInfo("America/New_York")


def positive(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def transient_missing(f, prefix):
    status = str(f.get(f"_{prefix}_status") or "")
    return any(reason in status for reason in ("request budget", "enrichment budget", "endpoint cooldown", "HTTP 429", "ReadTimeout", "ConnectTimeout", "ReadError", "ConnectError"))


def recover_market_evidence(bundle, saved):
    """Retain validated Finnhub P/E/profile observations for their existing 6h TTL.

    Only transient refresh failures qualify. Never reuse price, volume, SEC
    ratios, consensus scores or targets; never advance an observation timestamp.
    """
    f = bundle.setdefault("fundamentals", {})
    if bundle.get("currency", "USD") != "USD":
        return bundle
    try:
        now = datetime.fromisoformat(str(bundle["asof"]).replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return bundle
    for prefix, fields in (("valuation", ("trailingPE",)), ("market_cap", ("marketCap", "sharesOutstanding"))):
        if not transient_missing(f, prefix) or f.get(fields[0]) is not None:
            continue
        if prefix == "valuation" and f.get("forwardPE") is not None:
            continue
        candidates, superseded_at = [], None
        for payload in saved:
            if not isinstance(payload, dict):
                continue
            old = payload.get("fundamentals") or {}
            if payload.get("symbol") != bundle.get("symbol") or payload.get("currency", "USD") != "USD":
                continue
            if not str(old.get(f"_{prefix}_source") or "").startswith("Finnhub "):
                continue
            try:
                observed = datetime.fromisoformat(str(old.get(f"_{prefix}_asof") or "").replace("Z", "+00:00"))
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                if 0 <= (now-observed).total_seconds() < 21600:
                    if prefix == "valuation" and "positive TTM P/E not returned" in str(old.get("_valuation_status") or ""):
                        superseded_at = max(superseded_at, observed) if superseded_at else observed
                    elif positive(old.get(fields[0])):
                        candidates.append((observed, old))
            except (ValueError, TypeError):
                continue
        candidates = [item for item in candidates if superseded_at is None or item[0] > superseded_at]
        if not candidates:
            continue
        _, old = max(candidates, key=lambda item: item[0])
        failed_status = f.get(f"_{prefix}_status")
        for key in fields:
            if f.get(key) is None and positive(old.get(key)):
                f[key] = old[key]
        for suffix in ("source", "asof"):
            f[f"_{prefix}_{suffix}"] = old[f"_{prefix}_{suffix}"]
        f[f"_{prefix}_status"] = f"available (cached validated evidence; refresh {failed_status})"
        sources = bundle.get("data_sources")
        if isinstance(sources, dict):
            sources[prefix] = {"source": f[f"_{prefix}_source"], "status": f[f"_{prefix}_status"], "asof": f[f"_{prefix}_asof"]}
    return bundle


class EndpointCache:
    """Compact per-provider cache with a shared request budget and failure cooldown."""
    def __init__(self):
        self.entries = {}
        self.requests = deque()
        self.blocked = {}
        self.lock = Lock()

    def fetch(self, client, endpoint, symbol, token, ttl, params=None):
        key = (endpoint, symbol)
        now = time.monotonic()
        with self.lock:
            entries = self.entries.setdefault(endpoint, OrderedDict())
            cached = entries.get(key)
            if cached and cached[0] > now:
                entries.move_to_end(key)
                return cached[1], cached[2]
            if max(self.blocked.get(endpoint, 0), self.blocked.get("*", 0)) > now:
                return None, "unavailable (endpoint cooldown)"
            while self.requests and self.requests[0][0] < now - 60:
                self.requests.popleft()
            if len(self.requests) >= 45:
                return None, "unavailable (request budget)"
            # Optional enrichment must leave room for recommendation scores.
            if endpoint != "recommendation" and sum(ep != "recommendation" for _, ep in self.requests) >= 15:
                return None, "unavailable (enrichment budget; recommendations reserved)"
            self.requests.append((now, endpoint))
        data, status = None, "unavailable"
        cooldown = 0
        try:
            response = client.get("https://finnhub.io/api/v1/stock/" + endpoint,
                                  params={"symbol": symbol, "token": token, **(params or {})})
            if response.status_code in (401, 403, 429):
                cooldown = 3600 if response.status_code in (401, 403) else 60
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, (dict, list)) or not data or (isinstance(data, dict) and data.get("error")):
                data, status = None, "unavailable (empty/error response)"
            else:
                status = "available"
                # The metric endpoint also returns large historical series. Retain
                # only fields used by this scorer, including provider identity.
                if endpoint == "metric":
                    data = {"symbol": data.get("symbol"), "metric": {"peTTM": (data.get("metric") or {}).get("peTTM")}}
                elif endpoint == "recommendation":
                    data = data[:1]
                elif endpoint == "profile2":
                    data = {k: data.get(k) for k in ("ticker", "currency", "marketCapitalization", "shareOutstanding")}
                elif endpoint == "price-target":
                    data = {k: data.get(k) for k in ("symbol", "targetMean", "targetLow", "targetHigh", "lastUpdated")}
        except Exception as exc:
            # Never include exception URLs: Finnhub tokens are query parameters.
            code = getattr(getattr(exc, "response", None), "status_code", None)
            status = f"unavailable (HTTP {code})" if code else f"unavailable ({type(exc).__name__})"
            data = None
        with self.lock:
            if cooldown:
                self.blocked[endpoint] = now + cooldown
                if cooldown == 60:
                    self.blocked["*"] = now + cooldown
            if isinstance(data, dict):
                data = {**data, "_retrieved_at": datetime.now(timezone.utc).isoformat()}
            entries = self.entries[endpoint]
            # A temporary account throttle must be retried when its cooldown
            # expires, rather than suppressing scores for an extra five minutes.
            failure_ttl = 60 if cooldown == 60 else 300
            entries[key] = (now + (ttl if data is not None else failure_ttl), data, status)
            entries.move_to_end(key)
            limit = 256 if endpoint == "recommendation" else 32 if endpoint == "price-target" else 128
            while len(entries) > limit:
                entries.popitem(last=False)
        return data, status


def matched_relative_volume(chart, quote_ts, now=None):
    """Compare only completed regular-session five-minute buckets at the same time."""
    result = {"relative_volume": None, "status": "unavailable", "source": "Yahoo Finance 5-minute chart",
              "basis": "same-time completed regular-session volume / mean of up to 20 prior sessions",
              "historical_sessions": 0}
    try:
        quote = datetime.fromtimestamp(float(quote_ts), timezone.utc).astimezone(NY)
        now = (now or datetime.now(timezone.utc)).astimezone(NY)
        if quote.date() != now.date() or quote.weekday() >= 5:
            raise ValueError("quote is not from the current trading date")
        if 570 <= now.hour * 60 + now.minute < 960 and not 0 <= (now - quote).total_seconds() <= 600:
            raise ValueError("stale exchange quote")
        cutoff = min(960, (quote.hour * 60 + quote.minute) // 5 * 5)
        if cutoff <= 570:
            raise ValueError("no completed regular-session interval")
        expected = set(range(570, cutoff, 5))
        timestamps = chart.get("timestamp") or []
        if len(timestamps) > 6000:
            raise ValueError("intraday bar limit exceeded")
        volumes = (((chart.get("indicators") or {}).get("quote") or [{}])[0]).get("volume") or []
        sessions = {}
        for i, ts in enumerate(timestamps):
            dt = datetime.fromtimestamp(float(ts), timezone.utc).astimezone(NY)
            minute = dt.hour * 60 + dt.minute
            if dt.date() > quote.date() or dt.weekday() >= 5 or minute not in expected or dt.second:
                continue
            try:
                volume = float(volumes[i])
                if not math.isfinite(volume) or volume < 0:
                    raise ValueError()
            except (IndexError, TypeError, ValueError):
                volume = None
            buckets = sessions.setdefault(dt.date(), {})
            if minute in buckets and buckets[minute] != volume:
                buckets[minute] = None
            else:
                buckets[minute] = volume
        def total(buckets):
            if set(buckets) != expected or any(v is None for v in buckets.values()):
                return None
            return sum(buckets.values())
        current = total(sessions.get(quote.date(), {}))
        history = [total(sessions[day]) for day in sorted(sessions) if day < quote.date()]
        history = [v for v in history if v is not None][-20:]
        result["historical_sessions"] = len(history)
        if current is None or len(history) < 10:
            raise ValueError("need complete current intervals and at least 10 matching historical sessions")
        baseline = sum(history) / len(history)
        if baseline <= 0 or not math.isfinite(baseline) or not math.isfinite(current):
            raise ValueError("nonpositive historical volume")
        result.update(relative_volume=current / baseline, status="available", asof=quote.isoformat(),
                      cutoff=f"{cutoff // 60:02d}:{cutoff % 60:02d} America/New_York",
                      current_volume=current, historical_average_volume=baseline)
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        result["status"] = f"unavailable ({exc})"
    return result
