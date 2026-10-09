"""Read-only research client with endpoint-cost accounting and redacted errors."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT_COSTS = {"user": 0, "exchange-symbol-list": 1, "eod": 1, "splits": 1}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never send a token to a redirected destination or incur hidden calls.
        return None


class ResearchClient:
    def __init__(self, ledger: Path, *, budget=12, request_limit=12, opener=None):
        self.ledger = ledger
        self.budget = budget
        self.request_limit = request_limit
        self.opener = opener or build_opener(NoRedirect())

    def reserve(self, endpoint, symbol):
        if endpoint not in ENDPOINT_COSTS:
            raise ValueError("Endpoint has no approved cost")
        cost = ENDPOINT_COSTS[endpoint]
        state = json.loads(self.ledger.read_text()) if self.ledger.exists() else {"calls": [], "reserved_units": 0}
        if state["reserved_units"] + cost > self.budget or len(state["calls"]) >= self.request_limit:
            raise RuntimeError("Experiment request/cost budget exhausted")
        state["reserved_units"] += cost
        state["calls"].append({"endpoint": endpoint, "symbol": symbol, "cost": cost,
                               "at": datetime.now(timezone.utc).isoformat()})
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.ledger.write_text(json.dumps(state, indent=2) + "\n")

    def get(self, endpoint, symbol="", **params):
        token = os.environ.get("EODHD_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError("EODHD_API_TOKEN is not configured")
        self.reserve(endpoint, symbol)
        path = endpoint + ("/" + quote(symbol, safe=".") if symbol else "")
        query = urlencode({**params, "api_token": token, "fmt": "json"})
        req = Request(f"https://eodhd.com/api/{path}?{query}",
                      headers={"User-Agent": "ACWI-IMI-data-quality-research/1.0"})
        try:
            with self.opener.open(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"EODHD HTTP status {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("EODHD connection failed") from None
        except (UnicodeError, json.JSONDecodeError):
            raise RuntimeError("EODHD returned malformed JSON") from None


def usage_summary(payload):
    """Persist only quota fields, never personal account details or credentials."""
    if not isinstance(payload, dict):
        raise ValueError("Malformed account response")
    used = int(payload["apiRequests"])
    limit = int(payload["dailyRateLimit"])
    if min(used, limit) < 0:
        raise ValueError("Invalid quota counters")
    day = str(payload["apiRequestsDate"])[:10]
    current_day = datetime.now(timezone.utc).date().isoformat()
    return {"api_requests_date": day, "reported_used_units": used,
            "daily_limit": limit, "reported_remaining_units": max(0, limit-used),
            "quota_date_is_current": day == current_day,
            "remaining_units_today": max(0, limit-used) if day == current_day else limit}
