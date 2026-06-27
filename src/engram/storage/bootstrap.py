"""One-shot bootstrap: seed the bootstrap tenant and ensure the Qdrant collection.

Idempotent. Safe to run on every `make migrate`.
"""

from __future__ import annotations

from engram.config import get_settings
from engram.storage.db import session_scope
from engram.storage.tenant_repo import TenantRepo
from engram.storage.vector_store import ensure_collection


def bootstrap_all() -> dict:
    s = get_settings()
    result: dict = {"tenant": None, "qdrant_collection": s.qdrant_collection}

    # 1) Qdrant collection (+ payload indexes)
    ensure_collection(dim=s.embedding_dim)

    # 2) bootstrap tenant / API key
    if s.engram_bootstrap_api_key and s.engram_bootstrap_network_id:
        with session_scope() as session:
            TenantRepo(session).upsert(
                api_key=s.engram_bootstrap_api_key,
                network_id=s.engram_bootstrap_network_id,
                name="bootstrap",
            )
        result["tenant"] = s.engram_bootstrap_network_id
    else:
        result["tenant"] = "SKIPPED (set ENGRAM_BOOTSTRAP_API_KEY + ENGRAM_BOOTSTRAP_NETWORK_ID)"

    return result
