"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    admin_audit,
    admin_content,
    admin_mail,
    auth,
    files,
    health,
    public,
    publications,
    runs,
    schedules,
    system,
    templates,
    uploads,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.origin import make_origin_check


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Portfolio and SAP analytics API",
        version=__version__,
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment != "production" else None,
    )
    app.middleware("http")(make_origin_check(settings.cors_origin_list))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    for router in (
        health.router,
        auth.router,
        admin_audit.router,
        admin_content.router,
        admin_mail.router,
        files.admin_router,
        files.public_router,
        public.router,
        uploads.router,
        runs.router,
        schedules.router,
        system.router,
        templates.router,
        publications.admin_router,
        publications.public_router,
    ):
        app.include_router(router)
    return app


app = create_app()
