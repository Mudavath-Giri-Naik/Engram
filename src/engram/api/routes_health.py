"""Health/liveness — also checks Postgres + Qdrant reachability."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from engram.storage.db import get_engine
from engram.storage.vector_store import get_qdrant

router = APIRouter()


@router.get("/health")
def health() -> dict:
    checks: dict[str, str] = {}

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["postgres"] = f"error: {type(e).__name__}"

    try:
        get_qdrant().get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["qdrant"] = f"error: {type(e).__name__}"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}
