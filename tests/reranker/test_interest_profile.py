"""Tests for recency and Zotero preference-rating weights."""

from datetime import datetime

import numpy as np
from omegaconf import open_dict

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.protocol import CorpusPaper
from zotero_arxiv_daily.reranker.base import BaseReranker
from zotero_arxiv_daily.reranker.interest_profile import (
    corpus_by_priority,
    rating_factor,
    weighted_corpus,
)


class StubReranker(BaseReranker):
    def __init__(self, config, sim_matrix):
        super().__init__(config)
        self._sim = sim_matrix

    def get_similarity_score(self, s1, s2):
        return self._sim


def _corpus(*, newest_rating=None, oldest_rating=None):
    return [
        CorpusPaper(
            title="Newest",
            abstract="new",
            added_date=datetime(2026, 2, 1),
            paths=[],
            preference_rating=newest_rating,
        ),
        CorpusPaper(
            title="Oldest",
            abstract="old",
            added_date=datetime(2026, 1, 1),
            paths=[],
            preference_rating=oldest_rating,
        ),
    ]


def test_default_rating_factors(config):
    assert rating_factor(1, config) == 0.5
    assert rating_factor(3, config) == 1.0
    assert rating_factor(None, config) == 1.0
    assert rating_factor(5, config) == 2.0


def test_unrated_corpus_preserves_legacy_recency_weights(config):
    corpus, weights = weighted_corpus(_corpus(), config)
    legacy = 1.0 / (1.0 + np.log10(np.arange(1, 3)))
    legacy /= legacy.sum()

    assert [paper.title for paper in corpus] == ["Newest", "Oldest"]
    np.testing.assert_allclose(weights, legacy)


def test_high_rating_can_outweigh_recency(config):
    corpus = _corpus(newest_rating=1, oldest_rating=5)
    assert [paper.title for paper in corpus_by_priority(corpus, config)] == [
        "Oldest",
        "Newest",
    ]

    # Candidate A matches only the recent 1-star item; B matches only the
    # older 5-star item. Preference weighting should rank B first.
    candidates = [
        make_sample_paper(title="A", url="https://example.test/a"),
        make_sample_paper(title="B", url="https://example.test/b"),
    ]
    sim = np.array([[1.0, 0.0], [0.0, 1.0]])
    ranked = StubReranker(config, sim).rerank(candidates, corpus)
    assert [paper.title for paper in ranked] == ["B", "A"]


def test_zero_strength_disables_rating_weight(config):
    with open_dict(config):
        config.reranker.corpus_weighting.rating_strength = 0

    corpus, weights = weighted_corpus(
        _corpus(newest_rating=1, oldest_rating=5), config
    )
    legacy = 1.0 / (1.0 + np.log10(np.arange(1, 3)))
    legacy /= legacy.sum()

    assert [paper.title for paper in corpus] == ["Newest", "Oldest"]
    np.testing.assert_allclose(weights, legacy)
