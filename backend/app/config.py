"""Runtime settings. Every value can be overridden with an environment variable.

Brand, domain and theme are config values on purpose: the name and the domain
are not decided yet, and changing them must not need a code change.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Brand (placeholder until the name is chosen) ---
    brand_name: str = "Layerkit"
    brand_tagline: str = "Pack the right layers for every stop."
    brand_domain: str = "localhost"
    support_email: str = "hello@example.com"
    theme: str = "yellow-black"
    currency: str = "EUR"

    # --- Core ---
    environment: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://vestiti:vestiti@localhost:5432/vestiti"
    secret_key: str = "dev-only-change-me"
    session_days: int = 30
    cookie_secure: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    public_base_url: str = "http://localhost:8080"

    # --- Weather (Open-Meteo, free, no key) ---
    weather_enabled: bool = True
    weather_timeout_s: float = 8.0
    openmeteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    openmeteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    openmeteo_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    climate_years: int = 5
    weather_cache_hours: int = 6

    # --- LLM: any OpenAI-compatible server (Ollama, llama.cpp, vLLM, LM Studio) ---
    llm_enabled: bool = True
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M"
    llm_api_key: str = "local"  # local servers ignore it; never commit a real key
    llm_timeout_s: float = 60.0
    llm_disable_thinking: bool = True  # Qwen3: append /no_think for fast JSON answers
    # "auto" talks to Ollama's native API when the server is Ollama (needed to raise the
    # context window per request), otherwise to the OpenAI-compatible /v1 API.
    llm_api: str = "auto"  # auto | ollama | openai
    llm_num_ctx_max: int = 32768  # largest context window we ask Ollama for (long itineraries)
    llm_long_timeout_s: float = 600.0  # cap for reading very long trip descriptions

    # --- Affiliate networks (empty = link goes out untracked, click still logged) ---
    amazon_associate_tag: str = ""
    amazon_domain: str = "www.amazon.com"
    awin_publisher_id: str = ""
    impact_account_sid: str = ""
    cj_publisher_id: str = ""
    avantlink_affiliate_id: str = ""

    # --- Admin ---
    admin_emails: list[str] = Field(default_factory=list)

    # --- Rate limits (in-memory, per process) ---
    auth_rate_limit_per_minute: int = 10
    ai_rate_limit_per_minute: int = 20

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
