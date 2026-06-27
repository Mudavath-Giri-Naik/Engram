"""Local, open-source embeddings.

Default backend is sentence-transformers (BAAI/bge-small-en-v1.5), which runs
locally — NO paid embedding API is ever called.

For environments where the heavyweight model can't be installed (e.g. very new
Python versions without torch wheels yet), set EMBEDDING_MODEL=hashing to use a
built-in deterministic feature-hashing embedder. It produces real, content-
dependent vectors (identical text -> identical vector) — not canned data — so the
full system runs end to end without torch. Use the real model for production
quality.

Embeddings are L2-normalized so cosine == dot product. BGE models want a short
instruction prefix on the *query* side; we apply it to queries only.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from engram.config import get_settings

_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
_HASHING_NAMES = {"hashing", "local-hash", "hash", "none"}


def _is_hashing(model_name: str) -> bool:
    return model_name.strip().lower() in _HASHING_NAMES


def _hash_vector(text: str, dim: int) -> list[float]:
    v = [0.0] * dim
    words = re.findall(r"[a-z0-9_]+", text.lower())
    toks = list(words) + [w[i : i + 3] for w in words for i in range(max(0, len(w) - 2))]
    for tok in toks:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


@lru_cache(maxsize=1)
def _model():  # type: ignore[no-untyped-def]
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


class Embedder:
    """Thin wrapper around the configured embedding backend."""

    def __init__(self) -> None:
        s = get_settings()
        self.model_name = s.embedding_model
        self._hashing = _is_hashing(self.model_name)
        self._dim = s.embedding_dim

    @property
    def dim(self) -> int:
        if self._hashing:
            return self._dim
        return int(_model().get_sentence_embedding_dimension())

    def embed_document(self, text: str) -> list[float]:
        if self._hashing:
            return _hash_vector(text, self._dim)
        return _model().encode(text, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        if self._hashing:
            return _hash_vector(text, self._dim)
        return _model().encode(_QUERY_INSTRUCTION + text, normalize_embeddings=True).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self._hashing:
            return [_hash_vector(t, self._dim) for t in texts]
        return [v.tolist() for v in _model().encode(texts, normalize_embeddings=True)]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
