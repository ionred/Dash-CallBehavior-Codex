"""Application factory for the Dash app."""
from __future__ import annotations

import logging
from typing import Any

from dash import Dash
from flask import Flask
from flask_caching import Cache

from config import AppConfig, get_config
from app.data_access.sql_repository import SqlRepository
from app.layouts.main_layout import layout
from app.services.cache_service import CacheService
from app.services.event_service import EventService
from app.callbacks import register_callbacks

logger = logging.getLogger(__name__)

CACHE = Cache()


def create_flask_app(config: AppConfig) -> Flask:
    server = Flask(__name__)
    cache_config: dict[str, Any] = {"CACHE_TYPE": config.cache.type, "CACHE_DEFAULT_TIMEOUT": config.cache.default_timeout}
    if config.cache.directory:
        cache_config["CACHE_DIR"] = str(config.cache.directory)
    if config.cache.redis_url:
        cache_config["CACHE_REDIS_URL"] = config.cache.redis_url

    CACHE.init_app(server, config=cache_config)
    server.config["APP_CONFIG"] = config
    return server


def create_dash_app() -> Dash:
    config = get_config()
    server = create_flask_app(config)

    dash_app = Dash(
        __name__,
        server=server,
        suppress_callback_exceptions=True,
        title="Event Call Monitoring",
    )
    dash_app.layout = layout()

    repository = SqlRepository(config)
    cache_service = CacheService(CACHE)
    event_service = EventService(config, repository, cache_service)

    register_callbacks(dash_app, event_service)

    return dash_app


app = create_dash_app()
server = app.server

