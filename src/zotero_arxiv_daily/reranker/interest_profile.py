"""Build a weighted interest profile from a user's Zotero corpus."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..protocol import CorpusPaper


def _weighting_config(config):
    reranker = getattr(config, "reranker", None)
    if reranker is None:
        return None
    return reranker.get("corpus_weighting")


def rating_enabled(config) -> bool:
    cfg = _weighting_config(config)
    return bool(cfg.get("rating_enabled", True)) if cfg is not None else True


def rating_strength(config) -> float:
    cfg = _weighting_config(config)
    return float(cfg.get("rating_strength", 1.0)) if cfg is not None else 1.0


def unrated_value(config) -> int:
    cfg = _weighting_config(config)
    value = int(cfg.get("unrated_value", 3)) if cfg is not None else 3
    return min(5, max(1, value))


def has_active_ratings(corpus: Sequence[CorpusPaper], config) -> bool:
    """Whether rating metadata should affect this corpus."""

    return rating_enabled(config) and rating_strength(config) != 0.0 and any(
        paper.preference_rating is not None for paper in corpus
    )


def rating_factor(rating: int | None, config) -> float:
    """Map a 1-5 preference rating to a positive, configurable multiplier.

    With the default strength, 1/3/5 stars map to 0.5/1.0/2.0. Missing
    ratings use ``unrated_value`` (3 by default). A strength of zero disables
    the effect without changing the rest of the scoring pipeline.
    """

    if not rating_enabled(config):
        return 1.0
    value = unrated_value(config) if rating is None else min(5, max(1, rating))
    return 2.0 ** (rating_strength(config) * (value - 3) / 2.0)


def weighted_corpus(
    corpus: Sequence[CorpusPaper], config
) -> tuple[list[CorpusPaper], np.ndarray]:
    """Return the corpus in recency order and normalized combined weights."""

    ordered = sorted(corpus, key=lambda paper: paper.added_date, reverse=True)
    if not ordered:
        return [], np.array([], dtype=float)

    recency = 1.0 / (1.0 + np.log10(np.arange(1, len(ordered) + 1)))
    rating = np.array(
        [rating_factor(paper.preference_rating, config) for paper in ordered],
        dtype=float,
    )
    combined = recency * rating
    return ordered, combined / combined.sum()


def corpus_by_priority(corpus: Sequence[CorpusPaper], config) -> list[CorpusPaper]:
    """Order corpus items by their combined recency/rating importance."""

    ordered, weights = weighted_corpus(corpus, config)
    return [
        paper
        for paper, _ in sorted(
            zip(ordered, weights), key=lambda pair: pair[1], reverse=True
        )
    ]
