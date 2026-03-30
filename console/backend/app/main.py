from __future__ import annotations

from fastapi import FastAPI

from .api.jobs import router as jobs_router
from .api.packages import router as packages_router
from .api.settings import router as settings_router
from .dependencies import get_repository


def create_app() -> FastAPI:
    app = FastAPI(title="Job Console API", version="0.1.0")
    get_repository().ensure_schema()
    app.include_router(jobs_router)
    app.include_router(packages_router)
    app.include_router(settings_router)

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
