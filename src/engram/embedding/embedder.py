"""Local, open-source embeddings via sentence-transformers.

NO paid embedding API is ever called. The model (default BAAI/bge-small-en-v1.5)
runs locally. The model is loaded lazily and cached for the process lifetime.

BGE models recommend a short instruction prefix on the *query* side for
retrieval; we apply it to queries but not to stored documents, per the model
card. Embeddings are L2-normalized so cosine == dot product.
"""

from __future__ import annotations

from functools import lru_cache

from engram.config import get_settings

# BGE retrieval instruction (applied to queries only).
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():  # type: ignore[no-untyped-def]
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


class Embedder:
    """Thin wrapper around a sentence-transformers model."""

    def __init__(self) -> None:
        self.model_name = get_settings().embedding_model

    @property
    def dim(self) -> int:
        return int(_model().get_sentence_embedding_dimension())

    def embed_document(self, text: str) -> list[float]:
        vec = _model().encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_query(self, text: str) -> list[float]:
        vec = _model().encode(_QUERY_INSTRUCTION + text, normalize_embeddings=True)
        return vec.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = _model().encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
