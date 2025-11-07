"""Configuration management using environment variables (pydantic v2 style).

This file uses pydantic-settings' SettingsConfigDict via `model_config` to avoid
deprecated Field kwargs such as `env=` and the class-based Config.
"""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Model config (pydantic v2 recommended)
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Database
    db_path: str = "robot_trajectories.db"
    db_pool_size: int = 10
    # PRAGMA tuning (make configurable)
    cache_size: int = 64000  # KB (positive -> use negative value for page count PRAGMA)
    mmap_size: int = 0  # 0 means don't set mmap_size

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_workers: int = 4

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:8000"

    # Logging
    log_level: str = "INFO"

    # Application
    decimal_precision: int = 50
    default_tool_width: float = 0.1
    default_coverage_margin: float = 0.05

    # Optional MQTT broker for real-time events
    mqtt_enabled: bool = False
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_topic: str = "robot/trajectories"

    # Security
    api_key: str = (
        ""  # If set, write endpoints require this API key via X-API-Key or Bearer token
    )

    # DB maintenance
    checkpoint_interval_seconds: int = 300  # how often to run WAL checkpoint (seconds)
    vacuum_interval_seconds: int = 3600  # how often to run VACUUM (seconds)
    # Optional Redis URL for distributed rate-limiting (e.g., redis://localhost:6379/0)
    redis_url: str = ""
    # JWT authentication (optional)
    jwt_secret: str = ""
    jwt_exp_minutes: int = 60

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert comma-separated CORS origins to list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """Cache settings to avoid reading .env file repeatedly."""
    return Settings()
