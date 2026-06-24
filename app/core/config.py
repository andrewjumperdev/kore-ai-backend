"""Centralized, validated configuration loaded once at process start."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    env: str = "development"
    debug: bool = False
    secret_key: str = "dev-secret-change-me"
    api_v1_prefix: str = "/api/v1"
    project_name: str = "Kore AI"
    # URL pública del backend, alcanzable por proveedores externos (webhooks de
    # Evolution, etc.). En local con Evolution en docker y backend en el host:
    # host.docker.internal. En producción: tu dominio.
    public_base_url: str = Field(
        default="http://host.docker.internal:8000", alias="PUBLIC_BASE_URL"
    )

    # Datastores
    postgres_dsn: str = "postgresql+asyncpg://kore:kore@localhost:5432/kore"
    redis_url: str = "redis://localhost:6379/0"
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # LLM (these read non-prefixed env vars too, see Field aliases)
    # Provider activo: "openai" | "anthropic". Cada uno usa su key + modelo.
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"        # modelo Anthropic
    openai_model: str = "gpt-4o"                # modelo OpenAI
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Billing
    stripe_api_key: str = Field(default="", alias="STRIPE_API_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")

    # Channels
    whatsapp_api_url: str = Field(default="", alias="WHATSAPP_API_URL")
    whatsapp_phone_number_id: str = Field(default="", alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_access_token: str = Field(default="", alias="WHATSAPP_ACCESS_TOKEN")
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(default="growth@kore.ai", alias="EMAIL_FROM")

    # Customer Service agent (FAUSTO) — todas opcionales: cada integración se
    # activa sola cuando su credencial está presente; sin ella hace skip seguro.
    cs_buffer_seconds: int = 8  # ventana de agregación de mensajes múltiples
    # Evolution API (WhatsApp no oficial)
    evolution_api_url: str = Field(default="", alias="EVOLUTION_API_URL")
    evolution_api_key: str = Field(default="", alias="EVOLUTION_API_KEY")
    evolution_instance: str = Field(default="Fausto", alias="EVOLUTION_INSTANCE")
    # Secreto compartido para verificar el webhook entrante (?token= o header
    # x-webhook-token). Vacío = sin verificación (dev). En producción, setéalo.
    evolution_webhook_token: str = Field(default="", alias="EVOLUTION_WEBHOOK_TOKEN")
    # Google Calendar — id del calendario + auth.
    google_calendar_id: str = Field(default="", alias="GOOGLE_CALENDAR_ID")
    # Producción: refresh-token OAuth (no expira); se mintea/cachea el access token.
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_refresh_token: str = Field(default="", alias="GOOGLE_REFRESH_TOKEN")
    # Dev/fallback: access token estático (vence en ~1h).
    google_calendar_token: str = Field(default="", alias="GOOGLE_CALENDAR_TOKEN")
    cs_timezone: str = Field(default="Europe/Paris", alias="CS_TIMEZONE")
    cs_meeting_minutes: int = 30  # duración de la reunión agendada
    # ElevenLabs (voz)
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
