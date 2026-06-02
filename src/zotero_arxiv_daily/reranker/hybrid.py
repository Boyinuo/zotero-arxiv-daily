"""Hybrid reranker — blends bi-encoder embedding similarity with cross-encoder
rerank scores for the best of both worlds.

The embedding path (api_embedding) provides precise time-decayed similarity
against every Zotero paper, while the cross-encoder path (api_rerank) brings
deeper semantic understanding of (query, document) pairs.  The final score is
a configurable weighted blend of the two.
"""

from __future__ import annotations

import numpy as np

from omegaconf import DictConfig
from .base import BaseReranker, register_reranker
from .api import ApiEmbeddingReranker
from .api_rerank import ApiRerankReranker
from ..protocol import Paper, CorpusPaper


def _minmax_normalize(scores: np.ndarray) -> np.ndarray:
    """Scale *scores* to [0, 1] via min-max normalization.

    If all scores are identical they are mapped to 0.5.
    """
    smin, smax = scores.min(), scores.max()
    if smax - smin < 1e-8:
        return np.full_like(scores, 0.5)
    return (scores - smin) / (smax - smin)


@register_reranker("hybrid")
class HybridReranker(BaseReranker):
    """Combine api_embedding (bi-encoder) and api_rerank (cross-encoder) scores.

    Configuration (under ``reranker.hybrid``)::

        reranker:
          hybrid:
            embedding_weight: 0.5   # weight for the embedding path (0–1)
            rerank_weight: 0.5       # weight for the cross-encoder path (0–1)

    The *reranker.api_embedding* and *reranker.api_rerank* blocks are still
    used for the sub-reranker credentials / models.
    """

    def __init__(self, config: DictConfig):
        super().__init__(config)
        self._embedding = ApiEmbeddingReranker(config)
        self._cross = ApiRerankReranker(config)

    def get_similarity_score(self, s1: list[str], s2: list[str]) -> np.ndarray:
        """Not used — hybrid overrides ``rerank()`` directly."""
        raise NotImplementedError

    def rerank(
        self, candidates: list[Paper], corpus: list[CorpusPaper]
    ) -> list[Paper]:
        cfg = self.config.reranker.hybrid

        # ── 1.  Embedding-based scores (includes time-decay via base.rerank) ──
        emb_scores = _get_embedding_scores(self._embedding, candidates, corpus)

        # ── 2.  Cross-encoder scores ──
        cross_scores = _get_rerank_scores(self._cross, candidates, corpus)

        # ── 3.  Normalize & blend ──
        emb_norm = _minmax_normalize(emb_scores)
        cross_norm = _minmax_normalize(cross_scores)

        w_emb = cfg.get("embedding_weight", 0.5)
        w_cross = cfg.get("rerank_weight", 0.5)
        blended = emb_norm * w_emb + cross_norm * w_cross

        for s, c in zip(blended, candidates):
            c.score = float(s * 10)  # scale back to 0–10 for display

        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


# — helpers —————————————————————————————————————————————————————————


def _get_embedding_scores(
    embedder: ApiEmbeddingReranker,
    candidates: list[Paper],
    corpus: list[CorpusPaper],
) -> np.ndarray:
    """Run the full embedding rerank path and extract raw scores."""
    # base.rerank() computes time_decay_weight internally, so we can't easily
    # bypass it.  Run it on a copy to avoid mutating the originals.
    import copy
    candidates_copy = copy.deepcopy(candidates)
    embedder.rerank(candidates_copy, corpus)
    return np.array([c.score for c in candidates_copy])


def _get_rerank_scores(
    cross: ApiRerankReranker,
    candidates: list[Paper],
    corpus: list[CorpusPaper],
) -> np.ndarray:
    """Run the cross-encoder rerank path and extract raw scores."""
    import copy
    candidates_copy = copy.deepcopy(candidates)
    cross.rerank(candidates_copy, corpus)
    return np.array([c.score for c in candidates_copy])
