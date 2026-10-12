"""GEMv1-only Render ASGI entry point.

Never import dual_momentum.main: it starts the separate Paper Model's workers
and database migrations. This service exposes ONLY GEM's existing read-only
dashboard and an unauthenticated liveness endpoint. It does not fetch Marketstack,
execute orders, or grant verification authority.
"""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from dual_momentum.gem_dashboard import router as gem_readonly_router

app = FastAPI(
    title="GEMv1 Read-only Dashboard",
    description="Isolated diagnostic dashboard. No live trading signals or order routing.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
_basic = HTTPBasic(auto_error=False)


def _auth_ready() -> bool:
    username = os.getenv("GEM_DASHBOARD_USERNAME", "").strip()
    password = os.getenv("GEM_DASHBOARD_PASSWORD", "")
    return len(username) >= 3 and len(password) >= 20


def require_gem_login(
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> None:
    # A missing/malformed secret must NOT disable authentication.
    if not _auth_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GEM dashboard authentication has not been configured",
        )
    username = os.environ["GEM_DASHBOARD_USERNAME"].strip()
    password = os.environ["GEM_DASHBOARD_PASSWORD"]
    if (
        credentials is None
        or not secrets.compare_digest(credentials.username.encode(), username.encode())
        or not secrets.compare_digest(credentials.password.encode(), password.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="GEMv1 Read Only"'},
        )


@app.get("/health")
def health():
    return {
        "service": "gem-v1-dashboard",
        "healthy": True,
        "auth_configured": _auth_ready(),
        "trading_enabled": False,
        "mode": "READ_ONLY",
    }


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/gem-trial", status_code=302)


# Router dependencies also protect all future GET routes added to GEM router.
app.include_router(gem_readonly_router, dependencies=[Depends(require_gem_login)])
