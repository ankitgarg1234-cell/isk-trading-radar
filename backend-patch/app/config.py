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
    scan_batch_size: int = int(os.getenv("SCAN_BATCH_SIZE", "28"))
    universe_prefilter_batch_size: int = int(os.getenv("UNIVERSE_PREFILTER_BATCH_SIZE", "120"))
    universe_deep_candidates: int = int(os.getenv("UNIVERSE_DEEP_CANDIDATES", "10"))
    discovery_deep_candidates: int = int(os.getenv("DISCOVERY_DEEP_CANDIDATES", "8"))
    priority_deep_limit: int = int(os.getenv("PRIORITY_DEEP_LIMIT", "12"))
    quick_scan_workers: int = int(os.getenv("QUICK_SCAN_WORKERS", "8"))
    disable_scanner: bool = _bool("DISABLE_SCANNER", False)
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "8"))
    # Browser live polling is intentionally slower than the scanner cadence.
    # The scanner already refreshes market decisions every ~2 minutes; polling
    # managed Postgres every 15 seconds wasted egress without improving decisions.
    live_poll_seconds: int = int(os.getenv("LIVE_POLL_SECONDS", "60"))
    dashboard_cache_seconds: int = int(os.getenv("DASHBOARD_CACHE_SECONDS", "600"))
    mobile_token_ttl_seconds: int = int(os.getenv("MOBILE_TOKEN_TTL_SECONDS", "2592000"))
    snapshot_interval_seconds: int = int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "3600"))
    snapshot_score_delta: float = float(os.getenv("SNAPSHOT_SCORE_DELTA", "5"))
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
