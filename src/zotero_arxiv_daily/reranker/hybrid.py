"""Hybrid reranker — blends bi-encoder embedding similarity with cross-encoder
rerank scores.

The embedding path (api_embedding) provides time-decayed cosine similarity
against every Zotero paper.  The cross-encoder path (api_rerank) provides
deeper semantic relevance via joint (query, document) scoring.

The final score is the arithmetic mean of the two raw 0–10 component scores.
That same score is used for sorting, email display, and star rendering.
"""

from __future__ import annotations

import numpy as np

from omegaconf import DictConfig
from .base import BaseReranker, register_reranker
from .api import ApiEmbeddingReranker
from .api_rerank import ApiRerankReranker
from ..protocol import Paper, CorpusPaper


@register_reranker("hybrid")
class HybridReranker(BaseReranker):
    """Combine api_embedding and api_rerank via their raw-score average."""

    def __init__(self, config: DictConfig):
        super().__init__(config)
        self._embedding = ApiEmbeddingReranker(config)
        self._cross = ApiRerankReranker(config)

    def get_similarity_score(self, s1: list[str], s2: list[str]) -> np.ndarray:
        raise NotImplementedError

    def rerank(
        self, candidates: list[Paper], corpus: list[CorpusPaper]
    ) -> list[Paper]:
        emb_raw = _raw_embedding_scores(self._embedding, candidates, corpus)
        cross_raw = _raw_rerank_scores(self._cross, candidates, corpus)

        for c in candidates:
            embedding_score = emb_raw.get(c.url, 0.0)
            rerank_score = cross_raw.get(c.url, 0.0)

            # One score drives ranking, email display, and star rendering.
            c.score = round((embedding_score + rerank_score) / 2, 1)
            c.embedding_score = round(embedding_score, 1)
            c.rerank_score = round(rerank_score, 1)

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates


# ——————————————————————————————————————————————————————————————————
# helpers
# ——————————————————————————————————————————————————————————————————


def _raw_embedding_scores(
    embedder: ApiEmbeddingReranker,
    candidates: list[Paper],
    corpus: list[CorpusPaper],
) -> dict[str, float]:
    """Embedding path: weighted cosine similarity with the interest profile.

    Each candidate's score is the weighted sum of cosine similarities
    against every Zotero paper, using combined recency/rating weights and
    scaled to 0–10.
    """
    raw = embedder.compute_scores(candidates, corpus)
    return {c.url: float(s) for c, s in zip(candidates, raw)}


def _raw_rerank_scores(
    cross: ApiRerankReranker,
    candidates: list[Paper],
    corpus: list[CorpusPaper],
) -> dict[str, float]:
    """Cross-encoder path: relevance_score × 10 per candidate."""
    raw = cross.compute_scores(candidates, corpus)
    return {c.url: float(s) for c, s in zip(candidates, raw)}
