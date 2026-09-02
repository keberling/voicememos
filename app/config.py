from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    APP_NAME: str = "Voice Portal"
    APP_BASE_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///./data/voiceportal.db"
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_MB: int = 25

    AZURE_AD_CLIENT_ID: str = ""
    AZURE_AD_CLIENT_SECRET: str = ""
    AZURE_AD_TENANT_ID: str = "common"
    ALLOWED_EMAILS: str = ""

    SHORTCUT_ICLOUD_URL: str = ""
    SHORTCUT_FILE_URL: str = ""
    SIGN_SHORTCUTS: bool = True
    HUBSIGN_URL: str = "https://hubsign.routinehub.services/sign"

    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "auto"
    STT_BASE_URL: str = ""
    STT_API_KEY: str = ""
    STT_MODEL: str = "whisper-1"

    DISABLE_WORKER: bool = False
    WORKER_POLL_SECONDS: float = 0.75

    @property
    def app_base_url(self) -> str:
        return self.APP_BASE_URL.rstrip("/")

    @property
    def ingest_url(self) -> str:
        return f"{self.app_base_url}/api/v1/ingest"

    @property
    def auth_callback_url(self) -> str:
        return f"{self.app_base_url}/auth/callback"

    @property
    def cookie_secure(self) -> bool:
        return self.app_base_url.lower().startswith("https://")

    @property
    def upload_path(self) -> Path:
        return Path(self.UPLOAD_DIR).expanduser().resolve()

    @property
    def max_upload_bytes(self) -> int:
        return int(self.MAX_UPLOAD_MB) * 1024 * 1024

    @property
    def allowed_emails(self) -> set[str]:
        raw = (self.ALLOWED_EMAILS or "").strip()
        if not raw:
            return set()
        return {part.strip().lower() for part in raw.split(",") if part.strip()}

    @property
    def entra_configured(self) -> bool:
        return bool(self.AZURE_AD_CLIENT_ID and self.AZURE_AD_CLIENT_SECRET)

    @property
    def entra_tenant(self) -> str:
        tenant = (self.AZURE_AD_TENANT_ID or "common").strip()
        return tenant or "common"

    @property
    def entra_metadata_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.entra_tenant}"
            "/v2.0/.well-known/openid-configuration"
        )

    @property
    def stt_base_url(self) -> str:
        return _ensure_v1(self.STT_BASE_URL or self.LLM_BASE_URL)

    @property
    def stt_api_key(self) -> str:
        return self.STT_API_KEY or self.LLM_API_KEY

    @property
    def llm_base_url(self) -> str:
        return _ensure_v1(self.LLM_BASE_URL)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url)

    @property
    def hosted_shortcut_url(self) -> str:
        return f"{self.app_base_url}/shortcuts/Voice-Dump.shortcut"

    @property
    def hosted_share_sheet_shortcut_url(self) -> str:
        return f"{self.app_base_url}/shortcuts/Process-Voice-Memo.shortcut"

    @property
    def shortcut_file_url(self) -> str:
        return (self.SHORTCUT_FILE_URL or self.hosted_shortcut_url).strip()

    @property
    def shortcut_add_url(self) -> str:
        return (self.SHORTCUT_ICLOUD_URL or self.shortcut_file_url).strip()

    @property
    def shortcut_import_url(self) -> str:
        url = self.shortcut_file_url
        if not url:
            return ""
        from urllib.parse import quote

        return (
            "shortcuts://import-shortcut?url="
            f"{quote(url, safe='')}&name=Voice%20Dump"
        )


def _ensure_v1(url: str) -> str:
    """LLMrouterVEX (and OpenAI-compatible routers) serve under /v1."""
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
