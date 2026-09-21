"""Tests for the cross-encoder interest-query construction."""

from datetime import datetime

from omegaconf import open_dict

from zotero_arxiv_daily.protocol import CorpusPaper
from zotero_arxiv_daily.reranker.api_rerank import ApiRerankReranker


def _rated_corpus():
    return [
        CorpusPaper(
            title="Recent low preference",
            abstract="recent abstract",
            added_date=datetime(2026, 2, 1),
            paths=[],
            preference_rating=1,
        ),
        CorpusPaper(
            title="Older high preference",
            abstract="older abstract",
            added_date=datetime(2026, 1, 1),
            paths=[],
            preference_rating=5,
        ),
    ]


def test_interest_query_prioritizes_and_labels_ratings(config):
    query = ApiRerankReranker._build_interest_query(
        _rated_corpus(), max_tokens=1000, config=config
    )

    assert "higher preference rating" in query
    assert "[Preference: 5/5]" in query
    assert "[Preference: 1/5]" in query
    assert query.index("Older high preference") < query.index("Recent low preference")


def test_zero_rating_strength_preserves_legacy_query(config):
    with open_dict(config):
        config.reranker.corpus_weighting.rating_strength = 0

    query = ApiRerankReranker._build_interest_query(
        _rated_corpus(), max_tokens=1000, config=config
    )

    assert "Preference:" not in query
    assert query.index("Recent low preference") < query.index("Older high preference")
