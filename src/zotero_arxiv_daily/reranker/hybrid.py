"""Hybrid reranker — blends bi-encoder embedding similarity with cross-encoder
rerank scores for the best of both worlds.

The embedding path (api_embedding) provides precise time-decayed similarity
against every Zotero paper, while the cross-encoder path (api_rerank) brings
deeper semantic understanding of (query, document) pairs.

Fusion uses **Reciprocal Rank Fusion (RRF)** — a standard technique that is
immune to score-distribution mismatches.  A paper that ranks well in *either*
path gets a boost, while a paper that ranks poorly in both is penalised.
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
    """Combine api_embedding (bi-encoder) and api_rerank (cross-encoder) scores.

    Configuration (under ``reranker.hybrid``)::

        reranker:
          hybrid:
            k: 60               # RRF smoothing constant (default 60)
    """

    def __init__(self, config: DictConfig):
        super().__init__(config)
        self._embedding = ApiEmbeddingReranker(config)
        self._cross = ApiRerankReranker(config)

    def get_similarity_score(self, s1: list[str], s2: list[str]) -> np.ndarray:
        """Not used — hybrid overrides ``rerank()`` directly."""
        raise NotImplementedError

    # ——————————————————————————————————————————————————————————————
    # public API
    # ——————————————————————————————————————————————————————————————

    def rerank(
        self, candidates: list[Paper], corpus: list[CorpusPaper]
    ) -> list[Paper]:
        k = self.config.reranker.hybrid.get("k", 60)

        # ── 1.  Score each paper via both paths ──────────────────
        emb_rank = _score_and_rank(self._embedding, candidates, corpus, k)
        cross_rank = _score_and_rank(self._cross, candidates, corpus, k)

        # ── 2.  Reciprocal Rank Fusion ───────────────────────────
        for c in candidates:
            key = c.url
            c.score = float(emb_rank.get(key, 0) + cross_rank.get(key, 0))

        # ── 3.  Normalize RRF scores to 0–10 for display ─────────
        raw = np.array([c.score for c in candidates])
        smin, smax = raw.min(), raw.max()
        if smax - smin > 1e-8:
            scaled = (raw - smin) / (smax - smin) * 10
        else:
            scaled = np.full_like(raw, 5.0)
        for s, c in zip(scaled, candidates):
            c.score = float(s)

        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


# ——————————————————————————————————————————————————————————————————
# helpers
# ——————————————————————————————————————————————————————————————————


def _score_and_rank(
    reranker: BaseReranker,
    candidates: list[Paper],
    corpus: list[CorpusPaper],
    k: int,
) -> dict[str, float]:
    """Run *reranker* on a copy of *candidates*, then convert scores into
    Reciprocal Rank Fusion contributions (``1 / (k + rank)``) keyed by
    ``paper.url``.
    """
    import copy

    # Work on copies so the originals are untouched
    cand_copy = copy.deepcopy(candidates)

    _run_rerank_unsorted(reranker, cand_copy, corpus)

    # Sort by score descending to assign ranks
    ranked = sorted(cand_copy, key=lambda c: c.score or 0, reverse=True)

    rrf: dict[str, float] = {}
    for rank_zero, paper in enumerate(ranked):
        rrf[paper.url] = 1.0 / (k + rank_zero + 1)  # rank starts at 1
    return rrf


def _run_rerank_unsorted(
    reranker: BaseReranker,
    candidates: list[Paper],
    corpus: list[CorpusPaper],
) -> None:
    """Run the appropriate scoring path without relying on the default
    sort-the-candidates-in-place behaviour.
    """
    from .api import ApiEmbeddingReranker
    from .api_rerank import ApiRerankReranker

    if isinstance(reranker, ApiEmbeddingReranker):
        # Replicate BaseReranker.rerank() logic but don't sort at the end
        corpus_by_date = sorted(corpus, key=lambda x: x.added_date, reverse=True)
        time_decay = 1.0 / (1.0 + np.log10(np.arange(1, len(corpus_by_date) + 1)))
        time_decay = time_decay / time_decay.sum()

        c_texts = [c.title + " " + c.abstract for c in candidates]
        k_texts = [k.title + " " + k.abstract for k in corpus_by_date]

        sim = reranker.get_similarity_score(c_texts, k_texts)
        assert sim.shape == (len(candidates), len(corpus_by_date))
        raw = (sim * time_decay).sum(axis=1) * 10

        for s, c in zip(raw, candidates):
            c.score = float(s)

    elif isinstance(reranker, ApiRerankReranker):
        # The cross-encoder already sets scores per-paper, but it also
        # sorts the list.  Call its rerank() then read scores back by URL.
        import copy
        cand_copy = copy.deepcopy(candidates)
        reranker.rerank(cand_copy, corpus)
        score_by_url = {c.url: c.score for c in cand_copy}
        for c in candidates:
            c.score = score_by_url.get(c.url, 0.0)

    else:
        # Generic fallback — just call rerank() directly
        reranker.rerank(candidates, corpus)
