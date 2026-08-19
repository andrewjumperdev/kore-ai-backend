"""Centralized, validated configuration loaded once at process start.

En producción la config es *fail-fast*: si falta un secreto crítico o quedó un
default de desarrollo, el proceso NO arranca (ver ``_check_production``). Es
deliberado: preferimos un deploy que no levanta a uno que levanta inseguro.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Defaults que jamás deben llegar a producción.
INSECURE_SECRETS = {"dev-secret-change-me", "change-me", "secret", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Permite construir Settings(secret_key=…) además de por su alias/env.
        # Sin esto, los campos con alias solo se pueden setear por el alias, lo
        # que hace muy incómodo instanciar config en tests y scripts.
        populate_by_name=True,
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
    # OpenAPI/Swagger. En producción se apaga salvo que lo pidas explícitamente:
    # publica el mapa completo de la API (y de sus secretos de forma indirecta).
    docs_enabled: bool | None = None
    # Orígenes permitidos por CORS en producción, separados por coma. El
    # frontend habla con el backend server-side (BFF) → normalmente vacío.
    cors_origins: str = ""

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
    # Un LLM colgado bloquea un worker de gunicorn hasta el timeout de gunicorn
    # (60s). Cortamos antes y reintentamos los fallos transitorios.
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    # ── Seguridad ────────────────────────────────────────────────────
    # Estas tres toman el env_prefix KORE_ (KORE_PROVISIONING_SECRET, etc.);
    # no llevan alias explícito para no duplicar el nombre.
    #
    # Secreto que autoriza POST /tenants (provisioning). Lo conoce solo el BFF
    # del frontend; sin él cualquiera se autoprovisiona un tenant + API key.
    provisioning_secret: str = ""
    # Llave de operador para endpoints administrativos (cobros manuales, etc.).
    # NO es una API key de tenant: un cliente nunca debe poder usarla.
    admin_api_key: str = ""
    # Clave para cifrar credenciales de integraciones por tenant (SMTP, tokens…).
    # Vacía → se deriva de secret_key. Rotarla invalida lo ya cifrado.
    credentials_secret: str = ""

    # ── Rate limiting (Redis) ────────────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120            # global por IP
    rate_limit_agent_per_minute: int = 20       # POST /agents/run (gasta LLM)
    rate_limit_webhook_per_minute: int = 240    # por tenant, tráfico entrante
    rate_limit_tenant_create_per_hour: int = 20  # alta de tenants por IP
    # Techo mensual de tokens LLM por tenant (0 = sin límite). Protege el gasto
    # ante un tenant abusivo o un loop de mensajes.
    token_quota_monthly: int = 0

    # ── Observabilidad ───────────────────────────────────────────────
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = 0.0

    # Billing
    stripe_api_key: str = Field(default="", alias="STRIPE_API_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")

    # Channels
    whatsapp_api_url: str = Field(default="", alias="WHATSAPP_API_URL")
    whatsapp_phone_number_id: str = Field(default="", alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_access_token: str = Field(default="", alias="WHATSAPP_ACCESS_TOKEN")
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(default="growth@kore.ai", alias="EMAIL_FROM")

    # ── Webhooks entrantes ───────────────────────────────────────────
    # Secreto compartido genérico: todo webhook lo acepta vía ?token= o el header
    # x-webhook-token. Cada proveedor puede sobreescribirlo con el suyo.
    # En producción, un webhook SIN token efectivo responde 503 (fail-closed):
    # nunca procesa payload no autenticado.
    webhook_token: str = Field(default="", alias="WEBHOOK_TOKEN")
    plaud_webhook_token: str = Field(default="", alias="PLAUD_WEBHOOK_TOKEN")

    # Customer Service agent (FAUSTO) — todas opcionales: cada integración se
    # activa sola cuando su credencial está presente; sin ella hace skip seguro.
    cs_buffer_seconds: int = 8  # ventana de agregación de mensajes múltiples
    # Evolution API (WhatsApp no oficial)
    evolution_api_url: str = Field(default="", alias="EVOLUTION_API_URL")
    evolution_api_key: str = Field(default="", alias="EVOLUTION_API_KEY")
    evolution_instance: str = Field(default="Fausto", alias="EVOLUTION_INSTANCE")
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

    # Cold email / prospección — SMTP de salida (skip seguro sin host)
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    prospecting_batch_size: int = 5
    # Persona del icebreaker (valores por defecto = los del flujo n8n)
    icebreaker_sender_name: str = Field(default="Andrew Alfaro", alias="ICEBREAKER_SENDER_NAME")
    icebreaker_company: str = Field(default="Jumper Enterprise", alias="ICEBREAKER_COMPANY")
    icebreaker_cta_url: str = Field(
        default="https://agents-ai.andrewcr.com/", alias="ICEBREAKER_CTA_URL"
    )

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def serve_docs(self) -> bool:
        """Swagger/OpenAPI: on por defecto salvo en producción."""
        return (not self.is_production) if self.docs_enabled is None else self.docs_enabled

    @property
    def cors_allow_origins(self) -> list[str]:
        if not self.is_production:
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def webhook_token_for(self, provider: str) -> str:
        """Token efectivo de un webhook: el del proveedor, o el genérico."""
        override = {
            "evolution": self.evolution_webhook_token,
            "plaud": self.plaud_webhook_token,
        }.get(provider, "")
        return override or self.webhook_token

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if not self.is_production:
            return self
        problems: list[str] = []
        if self.secret_key in INSECURE_SECRETS or len(self.secret_key) < 32:
            problems.append(
                "KORE_SECRET_KEY es un default inseguro o muy corto "
                "(mínimo 32 chars: `openssl rand -hex 32`)"
            )
        if not self.provisioning_secret:
            problems.append(
                "KORE_PROVISIONING_SECRET vacío: POST /tenants quedaría abierto "
                "a cualquiera (autoprovisioning + gasto de LLM)"
            )
        if not self.webhook_token and not self.evolution_webhook_token:
            problems.append(
                "WEBHOOK_TOKEN vacío: los webhooks entrantes no podrían "
                "autenticarse y responderán 503"
            )
        if self.evolution_api_url and not self.webhook_token_for("evolution"):
            problems.append("EVOLUTION_WEBHOOK_TOKEN vacío con Evolution activa")
        if self.stripe_api_key and not self.stripe_webhook_secret:
            problems.append(
                "STRIPE_WEBHOOK_SECRET vacío con Stripe activo: no se podrían "
                "verificar los eventos de pago"
            )
        if self.debug:
            problems.append("KORE_DEBUG=true en producción (filtra internals)")
        if problems:
            raise ValueError(
                "Configuración inválida para env=production:\n  - "
                + "\n  - ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
