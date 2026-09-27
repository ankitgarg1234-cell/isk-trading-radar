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
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "120"))
    scan_batch_size: int = int(os.getenv("SCAN_BATCH_SIZE", "12"))
    disable_scanner: bool = _bool("DISABLE_SCANNER", False)
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "8"))
    live_poll_seconds: int = int(os.getenv("LIVE_POLL_SECONDS", "15"))
    radar_symbols: tuple[str, ...] = tuple(
        s.strip().upper()
        for s in os.getenv(
            "RADAR_SYMBOLS",
            "CRDO,SRRK,NVDA,AMD,AVGO,GOOGL,AMZN,META,UBER,PLTR,SMCI,TSLA",
        ).split(",")
        if s.strip()
    )

    @property
    def auth_enabled(self) -> bool:
        return bool(self.app_password)


settings = Settings()
