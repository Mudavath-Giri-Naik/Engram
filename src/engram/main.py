from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from engram.api import (
    routes_capture,
    routes_health,
    routes_incidents,
    routes_lab,
    routes_networks,
    routes_query,
)
def create_app() -> FastAPI:
    app = FastAPI(title="Engram", version="0.1.0", description="Network-specific incident memory.")
    oe=os.environ.get("CORS_ORIGINS","*").strip()
    origins=["*"] if oe=="*" else [o.strip() for o in oe.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    app.include_router(routes_health.router)
    app.include_router(routes_incidents.router, prefix="/v1")
    app.include_router(routes_query.router, prefix="/v1")
    app.include_router(routes_capture.router, prefix="/v1")
    app.include_router(routes_lab.router, prefix="/v1")
    app.include_router(routes_networks.router, prefix="/v1")
    return app
