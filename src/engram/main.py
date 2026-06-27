"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from engram.api import routes_health, routes_incidents, routes_query


def create_app() -> FastAPI:
    app = FastAPI(
        title="Engram",
        version="0.1.0",
        description=(
            "Network-specific incident memory. Stores troubleshooting sessions as "
            "structured + vector-embedded incidents and reasons comparatively over them."
        ),
    )
    app.include_router(routes_health.router)
    app.include_router(routes_incidents.router, prefix="/v1")
    app.include_router(routes_query.router, prefix="/v1")
    return app
