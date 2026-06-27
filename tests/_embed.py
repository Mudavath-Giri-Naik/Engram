"""Lightweight, deterministic embedder for tests.

This is a REAL embedding function (feature hashing of character n-grams into a
fixed-dim, L2-normalized vector), not a mock that returns canned data: identical
text yields identical vectors and similar text yields nearby vectors. It exists
so the test suite can validate the ingest/retrieval *plumbing* without
downloading the multi-hundred-MB sentence-transformers model in CI.

Production uses engram.embedding.embedder.Embedder (sentence-transformers).
"""

from __future__ import annotations

import hashlib
import math
import re

DIM = 384  # match the default production embedding dimension


def _tokens(text: str) -> list[str]:
    text = text.lower()
    words = re.findall(r"[a-z0-9_]+", text)
    grams: list[str] = list(words)
    for w in words:
        for i in range(len(w) - 2):
            grams.append(w[i : i + 3])
    return grams


class HashingEmbedder:
    model_name = "test-hashing-embedder"

    @property
    def dim(self) -> int:
        return DIM

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for tok in _tokens(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % DIM
            sign = 1.0 if (h >> 8) & 1 else -1.0
            v[idx] += sign
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_document(self, text: str) -> list[float]:
        return self._vec(text)

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]
