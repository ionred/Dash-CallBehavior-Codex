"""Application configuration module."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CacheConfig:
    """Configuration values for caching."""

    type: str
    directory: Optional[Path] = None
    default_timeout: int = 300
    redis_url: Optional[str] = None


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    server: str
    database: str
    timeout_seconds: int

    def connection_string(self) -> str:
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.server};DATABASE={self.database};Trusted_Connection=yes;"
        )


@dataclass
class AppConfig:
    """Primary application configuration container."""

    event_db: DatabaseConfig
    call_history_db: DatabaseConfig
    temp_db: DatabaseConfig
    cache: CacheConfig
    bulk_insert_timeout_seconds: int = 120
    sql_retry_attempts: int = 3


DEFAULT_CACHE_DIR = Path(".cache")


def get_config() -> AppConfig:
    """Return the default configuration for the application.

    File-system caching is enabled by default. To switch to Redis caching,
    update the :class:`CacheConfig` below with ``type="RedisCache"`` and
    provide the ``redis_url`` value. An example configuration is included in
    comments for convenience.
    """

    cache_directory = DEFAULT_CACHE_DIR
    cache_directory.mkdir(parents=True, exist_ok=True)

    file_system_cache = CacheConfig(
        type="FileSystemCache",
        directory=cache_directory,
        default_timeout=300,
    )

    # Example Redis configuration (currently unused):
    # redis_cache = CacheConfig(
    #     type="RedisCache",
    #     redis_url="redis://localhost:6379/0",
    #     default_timeout=300,
    # )

    event_db = DatabaseConfig(server="A1", database="MyLocalData", timeout_seconds=60)
    call_history_db = DatabaseConfig(server="B2", database="GenesysDB", timeout_seconds=90)
    temp_db = DatabaseConfig(server="B2", database="TempDB", timeout_seconds=90)

    return AppConfig(
        event_db=event_db,
        call_history_db=call_history_db,
        temp_db=temp_db,
        cache=file_system_cache,
        bulk_insert_timeout_seconds=180,
        sql_retry_attempts=3,
    )

