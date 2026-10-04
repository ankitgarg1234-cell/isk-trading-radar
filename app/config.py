import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./radar.db")
    session_secret: str = os.getenv("SESSION_SECRET", "dev-only-change-me")
    app_username: str = os.getenv("APP_USERNAME", "admin")
    app_password: str = os.getenv("APP_PASSWORD", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "ISK Trading Radar/1.0 contact@example.com")
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "120"))
    # Maximum number of symbols sent through the expensive full-analysis pipeline per cycle.
    # Broad-market coverage is handled separately by the rotating universe prefilter.
    scan_batch_size: int = int(os.getenv("SCAN_BATCH_SIZE", "32"))
    universe_prefilter_batch_size: int = int(os.getenv("UNIVERSE_PREFILTER_BATCH_SIZE", "200"))
    universe_deep_candidates: int = int(os.getenv("UNIVERSE_DEEP_CANDIDATES", "16"))
    discovery_deep_candidates: int = int(os.getenv("DISCOVERY_DEEP_CANDIDATES", "8"))
    priority_deep_limit: int = int(os.getenv("PRIORITY_DEEP_LIMIT", "8"))
    quick_scan_workers: int = int(os.getenv("QUICK_SCAN_WORKERS", "8"))
    disable_scanner: bool = _bool("DISABLE_SCANNER", False)
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "8"))
    # Browser live polling is intentionally slower than the scanner cadence.
    # The scanner already refreshes market decisions every ~2 minutes; polling
    # managed Postgres every 15 seconds wasted egress without improving decisions.
    live_poll_seconds: int = int(os.getenv("LIVE_POLL_SECONDS", "60"))
    dashboard_cache_seconds: int = int(os.getenv("DASHBOARD_CACHE_SECONDS", "600"))
    snapshot_interval_seconds: int = int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "3600"))
    snapshot_score_delta: float = float(os.getenv("SNAPSHOT_SCORE_DELTA", "5"))
    # Portfolio funnel: scan the full market internally and show at most 20 names.
    # Every Top-20 STRONG BUY / BUY / STARTER BUY is eligible for paper capital.
    # The shortlist is review-only. Legacy target/max/rank/rotation settings are
    # retained for deployment compatibility but no longer gate paper entries.
    optimizer_live_gating: bool = _bool("OPTIMIZER_LIVE_GATING", True)
    optimizer_visible_limit: int = int(os.getenv("OPTIMIZER_VISIBLE_LIMIT", "20"))
    optimizer_shortlist_limit: int = int(os.getenv("OPTIMIZER_SHORTLIST_LIMIT", "10"))
    optimizer_target_positions: int = int(os.getenv("OPTIMIZER_TARGET_POSITIONS", "6"))  # legacy, ignored for entry gating
    optimizer_max_positions: int = int(os.getenv("OPTIMIZER_MAX_POSITIONS", "7"))  # legacy, ignored for entry gating
    optimizer_min_rank_score: float = float(os.getenv("OPTIMIZER_MIN_RANK_SCORE", "62"))  # legacy, ignored for entry gating
    optimizer_rotation_gap: float = float(os.getenv("OPTIMIZER_ROTATION_GAP", "12"))  # legacy
    optimizer_rotation_yield_gap: float = float(os.getenv("OPTIMIZER_ROTATION_YIELD_GAP", "8"))  # legacy
    paper_trading_enabled: bool = _bool("PAPER_TRADING_ENABLED", True)
    score_band_trial_armed_at: str = os.getenv("SCORE_BAND_TRIAL_ARMED_AT", "")
    paper_starting_cash: float = float(os.getenv("PAPER_STARTING_CASH", "10000"))
    paper_trade_cost_bps: float = float(os.getenv("PAPER_TRADE_COST_BPS", "10"))
    paper_rebalance_seconds: int = int(os.getenv("PAPER_REBALANCE_SECONDS", "86400"))
    paper_snapshot_seconds: int = int(os.getenv("PAPER_SNAPSHOT_SECONDS", "1800"))
    # Government / strategic-capital monitor. This evidence is shadow-only until
    # walk-forward + forward paper testing proves incremental value versus SPY.
    strategic_capital_enabled: bool = _bool("STRATEGIC_CAPITAL_ENABLED", True)
    # PDF disclosure parsing is intentionally disabled in the live web/scanner
    # process by default. pypdf can temporarily consume hundreds of MB while
    # parsing the annual/periodic disclosure files, which exceeds the 512 MB
    # Render web-service limit and causes restart/502 loops. Lightweight
    # strategic/news/USAspending evidence remains enabled.
    strategic_disclosure_pdf_enabled: bool = _bool("STRATEGIC_DISCLOSURE_PDF_ENABLED", False)
    strategic_official_refresh_hours: int = int(os.getenv("STRATEGIC_OFFICIAL_REFRESH_HOURS", "24"))
    strategic_enrich_per_cycle: int = int(os.getenv("STRATEGIC_ENRICH_PER_CYCLE", "4"))
    strategic_enrich_interval_seconds: int = int(os.getenv("STRATEGIC_ENRICH_INTERVAL_SECONDS", "120"))
    strategic_error_retry_seconds: int = int(os.getenv("STRATEGIC_ERROR_RETRY_SECONDS", "600"))
    strategic_usaspending_max_attempts: int = int(os.getenv("STRATEGIC_USASPENDING_MAX_ATTEMPTS", "2"))
    strategic_usaspending_lookback_days: int = int(os.getenv("STRATEGIC_USASPENDING_LOOKBACK_DAYS", "730"))
    trump_oge_disclosure_url: str = os.getenv(
        "TRUMP_OGE_DISCLOSURE_URL",
        "https://oge.box.com/shared/static/zycb5i2ny8kssm51uzqm8ygyq2zkpkqq.pdf",
    )
    # Periodic transaction reports are separate from the annual OGE disclosure.
    # Keep this list configurable because new reports can be published during the year.
    trump_periodic_transaction_urls: tuple[str, ...] = tuple(
        u.strip()
        for u in os.getenv(
            "TRUMP_PERIODIC_TRANSACTION_URLS",
            "https://www.whitehouse.gov/wp-content/uploads/2026/03/President-Donald-J.-Trump-Periodic-Transaction-Report-2.26.26-1.pdf,"
            "https://www.whitehouse.gov/wp-content/uploads/2026/06/President-Donald-J.-Trump-Periodic-Transaction-Report-0.6.25.26-1.pdf,"
            "https://www.whitehouse.gov/wp-content/uploads/2026/06/President-Donald-J.-Trump-Periodic-Transaction-Report-0.6.25.26-2.pdf,"
            "https://www.whitehouse.gov/wp-content/uploads/2026/08/President-Donald-J.-Trump-Periodic-Transaction-Report-08.12.26.pdf",
        ).split(",")
        if u.strip()
    )
    whitehouse_investments_url: str = os.getenv(
        "WHITEHOUSE_INVESTMENTS_URL",
        "https://www.whitehouse.gov/investments/",
    )
    radar_symbols: tuple[str, ...] = tuple(
        s.strip().upper()
        for s in os.getenv(
            "RADAR_SYMBOLS",
            "",
        ).split(",")
        if s.strip()
    )

    @property
    def auth_enabled(self) -> bool:
        return bool(self.app_password)


settings = Settings()
