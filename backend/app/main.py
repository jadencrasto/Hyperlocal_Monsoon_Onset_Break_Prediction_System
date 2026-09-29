"""Run:  uvicorn app.main:create_app --factory --port 8000   (from the backend/ folder)"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import VERSION, router
from .config import Settings, get_settings
from .db import ensure_schema, make_engine, make_session_factory
from .models import Base
from .providers.registry import build_providers
from .services.weather_service import WeatherService


def create_app(settings: Settings | None = None, providers: dict | None = None, connectivity=None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    ensure_schema(engine)
    factory = make_session_factory(engine)
    kwargs = {"connectivity": connectivity} if connectivity else {}
    app = FastAPI(title="Hyperlocal Monsoon Onset & Break API (SIH26086)", version=VERSION)
    app.state.settings, app.state.session_factory = settings, factory
    app.state.service = WeatherService(factory, providers or build_providers(settings), settings, **kwargs)
    app.state.mode_pref = "auto"
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router, prefix="/api")
    return app
