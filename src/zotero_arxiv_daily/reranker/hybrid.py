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
    """Embedding path: weighted cosine similarity with time decay.

    Each candidate's score is the weighted sum of cosine similarities
    against every Zotero paper (newer papers weighted higher), scaled
    to 0–10.
    """
    corpus_by_date = sorted(corpus, key=lambda x: x.added_date, reverse=True)
    time_decay = 1.0 / (1.0 + np.log10(np.arange(1, len(corpus_by_date) + 1)))
    time_decay = time_decay / time_decay.sum()

    c_texts = [c.title + " " + c.abstract for c in candidates]
    k_texts = [k.title + " " + k.abstract for k in corpus_by_date]

    sim = embedder.get_similarity_score(c_texts, k_texts)
    assert sim.shape == (len(candidates), len(corpus_by_date))
    raw = (sim * time_decay).sum(axis=1) * 10

    return {c.url: float(s) for c, s in zip(candidates, raw)}


def _raw_rerank_scores(
    cross: ApiRerankReranker,
    candidates: list[Paper],
    corpus: list[CorpusPaper],
) -> dict[str, float]:
    """Cross-encoder path: relevance_score × 10 per candidate."""
    import copy
    cand_copy = copy.deepcopy(candidates)
    cross.rerank(cand_copy, corpus)
    return {c.url: c.score or 0.0 for c in cand_copy}
