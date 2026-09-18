"""Regression tests for hybrid reranking and score presentation."""

from tests.canned_responses import make_sample_corpus, make_sample_paper
from zotero_arxiv_daily.reranker.hybrid import HybridReranker, _to_quantiles


def test_hybrid_keeps_display_scores_consistent_with_order(config, monkeypatch):
    candidates = [
        make_sample_paper(title=name, url=f"https://example.test/{name}")
        for name in "ABCDE"
    ]
    embedding = dict(zip((p.url for p in candidates), [7.0, 5.0, 6.0, 4.0, 3.0]))
    cross = dict(zip((p.url for p in candidates), [6.0, 10.0, 5.0, 4.0, 3.0]))

    monkeypatch.setattr(
        "zotero_arxiv_daily.reranker.hybrid._raw_embedding_scores",
        lambda reranker, papers, corpus: embedding,
    )
    monkeypatch.setattr(
        "zotero_arxiv_daily.reranker.hybrid._raw_rerank_scores",
        lambda reranker, papers, corpus: cross,
    )

    ranked = HybridReranker(config).rerank(candidates, make_sample_corpus())

    assert [paper.title for paper in ranked] == ["A", "B", "C", "D", "E"]
    assert [paper.score for paper in ranked] == [8.8, 7.5, 6.2, 2.5, 0.0]
    assert [paper.score for paper in ranked] == sorted(
        (paper.score for paper in ranked), reverse=True
    )
    assert ranked[0].embedding_score == 7.0
    assert ranked[0].rerank_score == 6.0


def test_quantiles_give_ties_the_same_rank():
    assert _to_quantiles({"A": 1.0, "B": 1.0, "C": 3.0}) == {
        "A": 0.25,
        "B": 0.25,
        "C": 1.0,
    }
    assert _to_quantiles({"A": 7.0}) == {"A": 0.5}
