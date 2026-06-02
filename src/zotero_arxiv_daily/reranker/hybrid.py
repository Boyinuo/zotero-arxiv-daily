"""Hybrid reranker — blends bi-encoder embedding similarity with cross-encoder
rerank scores.

The embedding path (api_embedding) provides time-decayed cosine similarity
against every Zotero paper.  The cross-encoder path (api_rerank) provides
deeper semantic relevance via joint (query, document) scoring.

**Score calibration via quantile normalisation**

The two paths produce scores with very different distribution shapes
(embedding: narrow 2–7 band; rerank: wide 0.3–9.8 spread).  Simple averaging
would let the wider distribution dominate.

Instead, each path's scores are mapped to their **quantiles** within the
current batch of candidates.  Both paths then contribute equally on a
common [0, 1] scale, and the final score is the mean quantile × 10.
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
    """Combine api_embedding and api_rerank via quantile-normalised averaging."""

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

        # Map each path's scores to quantiles [0, 1]
        emb_q = _to_quantiles(emb_raw)
        cross_q = _to_quantiles(cross_raw)

        for c in candidates:
            qe = emb_q.get(c.url, 0)
            qx = cross_q.get(c.url, 0)
            c.score = round((qe + qx) / 2 * 10, 1)
            # Preserve raw scores for transparent display in the email
            c.embedding_score = round(emb_raw.get(c.url, 0), 1)
            c.rerank_score = round(cross_raw.get(c.url, 0), 1)

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates


# ——————————————————————————————————————————————————————————————————
# helpers
# ——————————————————————————————————————————————————————————————————


def _to_quantiles(scores: dict[str, float]) -> dict[str, float]:
    """Convert ``{url: raw_score}`` to ``{url: quantile_in_[0,1]}``.

    Uses *average* rank for ties so that papers with identical raw scores
    receive identical quantiles.
    """
    if len(scores) <= 1:
        return {url: 0.5 for url in scores}

    # Sort by score ascending; assign average rank for ties
    sorted_items = sorted(scores.items(), key=lambda x: x[1])
    n = len(sorted_items)

    result: dict[str, float] = {}
    i = 0
    while i < n:
        # Find the run of identical scores
        j = i
        while j < n and sorted_items[j][1] == sorted_items[i][1]:
            j += 1
        # Average rank across the tie group
        avg_rank = (i + j - 1) / 2  # 0-indexed ranks averaged
        quantile = avg_rank / (n - 1)
        for k in range(i, j):
            result[sorted_items[k][0]] = quantile
        i = j

    return result


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
