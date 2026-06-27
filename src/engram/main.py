"""FastAPI application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engram.api import routes_capture, routes_health, routes_incidents, routes_query


def create_app() -> FastAPI:
    app = FastAPI(
        title="Engram",
        version="0.1.0",
        description=(
            "Network-specific incident memory. Stores troubleshooting sessions as "
            "structured + vector-embedded incidents and reasons comparatively over them."
        ),
    )

    # CORS — lets a separately-deployed frontend (e.g. Vercel) call this API.
    # Set CORS_ORIGINS to a comma-separated list of allowed origins in prod;
    # defaults to "*" for easy local/demo use.
    origins_env = os.environ.get("CORS_ORIGINS", "*").strip()
    origins = ["*"] if origins_env == "*" else [o.strip() for o in origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_health.router)
    app.include_router(routes_incidents.router, prefix="/v1")
    app.include_router(routes_query.router, prefix="/v1")
    app.include_router(routes_capture.router, prefix="/v1")
    return app
