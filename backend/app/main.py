from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.rate_limit import register_rate_limiting
from app.core.spa import STATIC_DIR, install_security_headers, install_web_app
from app.routers import (
    auth,
    complaints,
    devices,
    events,
    health,
    reports,
    units,
    users,
)

API_PREFIX = "/api/v1"


def create_app(static_dir: Path = STATIC_DIR) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="LASRRA Engineering Audit System",
        version="0.1.0",
        docs_url="/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    register_rate_limiting(app)

    app.include_router(health.router, include_in_schema=False)  # /health for compose/proxy
    app.include_router(health.router, prefix=API_PREFIX)  # /api/v1/health
    for module in (auth, users, units, devices, complaints, events, reports):
        app.include_router(module.router, prefix=API_PREFIX)
    install_security_headers(app)
    install_web_app(app, static_dir)  # last: the catch-all /app mount must not shadow the API
    return app


app = create_app()
