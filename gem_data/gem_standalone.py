"""GEMv1-only Render ASGI entry point.

Never import dual_momentum.main: it starts the separate Paper Model's workers
and database migrations. This service exposes ONLY GEM's existing read-only
dashboard and an unauthenticated liveness endpoint. It does not fetch Marketstack,
execute orders, or grant verification authority.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from dual_momentum.gem_dashboard import router as gem_readonly_router
from gem_data.gem_manual_routes import router as gem_manual_router
from gem_data.gem_portfolio_routes import router as gem_portfolio_router

_log = logging.getLogger(__name__)


async def _public_source_loop():
    """Optional bounded ingestion loop for this single GEM-only Starter service.

    All network/database I/O happens off the ASGI event loop. No market-data
    or SEC calls, no ranking, never a trading system.
    """
    from gem_data.gem_public_ingest import capture_and_persist, next_daily_run
    while True:
        try:
            result = await asyncio.to_thread(capture_and_persist)
            _log.info("GEM isolated public source refresh states: %s", result)
        except Exception as exc:
            # Never log database URLs, credentials, vendor response content.
            _log.warning("GEM isolated source refresh failed (%s)", type(exc).__name__)
        delay = (next_daily_run(datetime.now(timezone.utc)) -
                 datetime.now(timezone.utc)).total_seconds()
        await asyncio.sleep(max(1.0, delay))


async def _sec_bulk_loop():
    """Isolated opt-in research task; no HTTP request can trigger ingestion.

    The real SEC archive is potentially multiple gigabytes. The only permitted
    path is strict validated 206 byte ranges of selected ZIP members.
    """
    from gem_data.sec_bulk_zip_ingest import capture_bulk_batch, BulkSourceHold
    await asyncio.sleep(25)  # avoid competing with startup public source scans
    while True:
        interval = 3600
        try:
            bound = int(os.getenv("GEM_SEC_BULK_CIK_LIMIT", "1"))
            report = await asyncio.to_thread(capture_bulk_batch, max_ciks=bound)
            # Aggregate coverage only, no private issuer/contact data in logs.
            _log.info("GEM SEC nightly ZIP selected member ingestion: %s", report)
            pending = sum(int(x["remaining_after_estimate"]) for x in report["kind"].values())
            interval = 3600 if pending == 0 else 300
        except BulkSourceHold as exc:
            # These error messages are deliberately fixed non-secret labels.
            _log.warning("GEM SEC ZIP ingestion HOLD: %s", str(exc)[:200])
        except Exception as exc:
            _log.warning("GEM SEC ZIP ingestion failed closed (%s)", type(exc).__name__)
        await asyncio.sleep(interval)


async def _sec_fact_qa_loop():
    """Separate, opt-in automated original-byte QA; NEVER SEC certification."""
    from gem_data.sec_fact_audit_worker import audit_batch, QAHold
    await asyncio.sleep(65)  # bulk ingestion gets first access to the service
    while True:
        interval = 3600
        try:
            bound = int(os.getenv("GEM_SEC_FACT_AUDIT_CIK_LIMIT", "5"))
            report = await asyncio.to_thread(audit_batch, max_pairs=bound)
            _log.info("GEM SEC independent machine QA (NOT certified): %s", report)
            if report["remaining_after_estimate"]:
                interval = 120
        except QAHold as exc:
            _log.warning("GEM SEC machine QA HOLD: %s", str(exc)[:160])
        except Exception as exc:
            _log.warning("GEM SEC machine QA failed closed (%s)", type(exc).__name__)
        await asyncio.sleep(interval)


@asynccontextmanager
async def _lifespan(app):
    tasks = []
    if os.getenv("GEM_PUBLIC_COLLECTION_ENABLED") == "yes":
        tasks.append(asyncio.create_task(_public_source_loop()))
    if os.getenv("GEM_SEC_BULK_ENABLED") == "yes":
        tasks.append(asyncio.create_task(_sec_bulk_loop()))
    if os.getenv("GEM_SEC_FACT_AUDIT_ENABLED") == "yes":
        tasks.append(asyncio.create_task(_sec_fact_qa_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    lifespan=_lifespan,
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
    return RedirectResponse(url="/gem-portfolio", status_code=302)


# Router dependencies also protect all future GET routes added to GEM router.
app.include_router(gem_readonly_router, dependencies=[Depends(require_gem_login)])
app.include_router(gem_manual_router, dependencies=[Depends(require_gem_login)])
app.include_router(gem_portfolio_router, dependencies=[Depends(require_gem_login)])
