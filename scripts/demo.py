"""Engram standalone demo — runs the whole system in-memory, no external services.

    python scripts/demo.py

No Docker, no Postgres/Qdrant install, no API key required. It uses:
  - SQLite (in-memory) for the structured store,
  - Qdrant in LOCAL in-memory mode for real vector search,
  - the real sentence-transformers embedder IF installed, otherwise a small
    built-in deterministic embedder so the demo always runs.

It seeds a few incidents (incl. one that FAILED) and runs the "85% like #47"
query end-to-end through the real FastAPI app, printing the retrieval result.
With LLM_PROVIDER/LLM_MODEL/LLM_API_KEY set in .env.local, the reasoning step
also returns the comparative analysis.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# make `import engram` work when run from the repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qm  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from engram.api import deps  # noqa: E402
from engram.main import create_app  # noqa: E402
from engram.storage.orm import Base, Tenant  # noqa: E402
from engram.storage.vector_store import VectorStore  # noqa: E402

DIM = 384


class _FallbackEmbedder:
    """Deterministic feature-hashing embedder (used only if sentence-transformers
    is not installed). Real, content-dependent vectors — not canned data."""

    model_name = "demo-hashing-embedder"

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        words = re.findall(r"[a-z0-9_]+", text.lower())
        toks = list(words) + [w[i : i + 3] for w in words for i in range(max(0, len(w) - 2))]
        for tok in toks:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % DIM] += 1.0 if (h >> 8) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    @property
    def dim(self) -> int:
        return DIM

    def embed_document(self, text: str) -> list[float]:
        return self._vec(text)

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


def _get_embedder():
    try:
        import sentence_transformers  # noqa: F401

        from engram.embedding.embedder import get_embedder

        emb = get_embedder()
        print(f"  embedder: real sentence-transformers ({emb.model_name})")
        return emb
    except Exception:
        print("  embedder: built-in deterministic (sentence-transformers not installed)")
        return _FallbackEmbedder()


def build_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SF = sessionmaker(bind=engine, expire_on_commit=False)
    s = SF()
    s.add(Tenant(api_key="DEMO-KEY", network_id="acme-core", name="demo", created_at=datetime.now(timezone.utc)))
    s.commit()
    s.close()

    qc = QdrantClient(":memory:")
    qc.create_collection("demo", vectors_config=qm.VectorParams(size=DIM, distance=qm.Distance.COSINE))
    vs = VectorStore(client=qc, collection="demo")
    emb = _get_embedder()

    app = create_app()

    def _db():
        x = SF()
        try:
            yield x
            x.commit()
        finally:
            x.close()

    app.dependency_overrides[deps.db_session] = _db
    app.dependency_overrides[deps.vector_store] = lambda: vs
    app.dependency_overrides[deps.embedder] = lambda: emb
    return TestClient(app)


def main() -> None:
    print("=== Engram standalone demo (in-memory, no Docker) ===")
    c = build_client()
    H = {"X-API-Key": "DEMO-KEY"}

    def add(title, desc, protocols, layer, devices, rc, fix, outcome, topo="topo-v1", days_ago=0):
        body = {
            "network_id": "x", "title": title,
            "symptom": {"description": desc, "protocols": protocols, "affected_layer": layer,
                        "scope": "LINK", "severity": "SEV2"},
            "context": {"devices": devices, "topology_hash": topo},
            "resolution": {"root_cause": rc, "fix_description": fix},
            "outcome": {"status": outcome, "verified": True, "mttr_seconds": 900},
            "occurred_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        }
        return c.post("/v1/incidents", headers=H, json=body).json()["id"]

    print("\nSeeding incidents for tenant 'acme-core':")
    i47 = add("#47 BGP neighbor down R2-R3", "BGP neighbor 10.0.23.3 to R3 stuck Active, never establishes",
              ["BGP"], "L3", ["R2", "R3"], "neighbor remote-as typo (65999)", "corrected remote-as to 65002", "RESOLVED")
    print(f"  #47 BGP neighbor down  -> {i47[:8]}  RESOLVED")
    add("MTU mismatch R1-R2", "OSPF adjacency stuck ExStart, mtu mismatch on link",
        ["OSPF", "MTU"], "L3", ["R1", "R2"], "eth1 mtu 9000 vs 1500", "set mtu 1500 both ends", "RESOLVED")
    print("  MTU mismatch           -> (RESOLVED)")
    fid = add("Old BGP fix that FAILED", "BGP neighbor down, tried clearing session, did not help",
              ["BGP"], "L3", ["R4"], "(wrong) suspected flap", "clear ip bgp * (FAILED)", "FAILED",
              topo="topo-OLD", days_ago=400)
    print(f"  Old BGP fix            -> {fid[:8]}  FAILED + stale")

    print("\n=== Query: a new fault that looks like #47 ===")
    q = {"network_id": "ignored",
         "description": "Site B (R3) not learning Site A routes; BGP session to R2 looks up; AS-path filtering suspected",
         "protocols": ["BGP"], "affected_layer": "L3", "devices": ["R3", "R2"], "current_topology_hash": "topo-v1"}
    data = c.post("/v1/query", headers=H, json=q).json()

    print(f"\nTop {len(data['retrieved'])} retrieved (ranked by final_score):")
    for i, r in enumerate(data["retrieved"], 1):
        inc = r["incident"]
        print(f"\n  [{i}] {inc['title']}")
        print(f"      final={r['final_score']:.3f} vector={r['vector_score']:.3f} structured={r['structured_score']:.3f}")
        print(f"      why : {r['match_explanation']}")
        if r["outcome_flag"]:
            print(f"      FLAG: {r['outcome_flag']}")
        if r["staleness"]["stale"]:
            print(f"      STALE: {', '.join(r['staleness']['reasons'])} (age {r['staleness']['age_days']}d)")

    print("\n=== Reasoning ===")
    if data.get("reasoning"):
        rs = data["reasoning"]
        print(f"  hypothesis: {rs['recommended_hypothesis']}")
        print(f"  fix       : {rs['recommended_fix']}")
        print(f"  confidence: {rs['confidence']}  | requires_human_approval: {rs['requires_human_approval']}")
        for w in rs.get("warnings", []):
            print(f"  warning   : {w}")
    else:
        print(f"  (LLM not configured) {data.get('reasoning_error')}")
        print("  Set LLM_PROVIDER / LLM_MODEL / LLM_API_KEY in .env.local to enable comparative reasoning.")

    print("\nDone. This ran the real API, retrieval, and stores entirely in memory.")


if __name__ == "__main__":
    main()
