"""Application settings (PRD §7). Every model ID, URL, timeout and limit comes from here."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed environment configuration. Values are read from env vars and `backend/.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Google Cloud
    GCP_PROJECT_ID: str = "demo-lastmile"
    GCP_REGION: str = "asia-southeast1"
    FIRESTORE_EMULATOR_HOST: str | None = None

    # GenAI. Free tier: GENAI_USE_VERTEX=false + an AI Studio key (docs/DECISIONS.md D-001).
    GENAI_MODE: Literal["fake", "real"] = "fake"
    GENAI_USE_VERTEX: bool = False
    VERTEX_LOCATION: str = "global"
    GEMINI_API_KEY: SecretStr | None = None
    LIVE_USE_AI_STUDIO: bool = True
    # Verified on the project key 2026-10-17 (D-044): 3.5-flash-lite answers; 2.5-flash-lite
    # works but its free daily quota runs out first, so it is the fallback (own quota).
    GEMINI_AGENT_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_LIVE_MODEL: str = "gemini-3.1-flash-live-preview"
    GEMINI_TTS_MODEL: str = "gemini-3.1-flash-tts-preview"
    GEMINI_RPM: int = 10

    # Demo access
    DEMO_PASSCODE: SecretStr = SecretStr("change-me")
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # [P2] Cloud Tasks
    TASKS_QUEUE: str = "lastmile-events"
    TASKS_INVOKER_SA: str | None = None
    SERVICE_URL: str | None = None

    # Simulation and limits
    SIM_TIME_SCALE: float = 10
    MAX_CONCURRENT_CHECKINS: int = 8
    MAX_ATTEMPTS: int = 3
    RETRY_DELAY_S: float = 120
    LIVE_RING_TIMEOUT_S: float = 120
    LIVE_MAX_CALL_S: float = 150
    # PRD §7 says 20 s; decisions queue behind classifier calls under GEMINI_RPM, so 20 s
    # timed out almost every decision on the deployed run (D-044).
    AGENT_TIMEOUT_S: float = 60
    AUTO_APPROVE_DISPATCH: bool = False
    SAFE_CONFIDENCE_MIN: float = 0.80
    SITREP_INTERVAL_S: float = 120
    INCIDENT_TTL_MIN: float = 30
    MAX_ACTIVE_INCIDENTS: int = 1
    RATE_LIMIT_PER_MIN: int = 30
    LOG_LEVEL: str = "INFO"

    # Feature switches
    TASKS_MODE: Literal["inline", "cloud"] = "inline"
    DECISION_ENGINE: Literal["structured", "adk"] = "structured"
    LIVE_MODE: Literal["voice", "text"] = "voice"
    SIM_DIALOGUE_MODE: Literal["cached", "single_call", "turns"] = "cached"
    PHASE: int = 1
    FORCE_FALLBACK: bool = False
    SIM_VOLUNTEERS: bool = True
    ORG_NAME: str = "Taman Sungai Indah Community Response (demo)"
    EMERGENCY_NUMBER: str = "999"

    VERSION: str = Field(default="0.1.0")

    @property
    def allowed_origins(self) -> list[str]:
        """CORS allow-list as a list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
