"""Regression tests for hybrid reranking and score presentation."""

from tests.canned_responses import make_sample_corpus, make_sample_paper
from zotero_arxiv_daily.construct_email import render_email
from zotero_arxiv_daily.reranker.hybrid import HybridReranker


def test_hybrid_uses_raw_average_for_order_display_and_stars(config, monkeypatch):
    candidates = [
        make_sample_paper(title=name, url=f"https://example.test/{name}")
        for name in ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
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

    assert [paper.title for paper in ranked] == [
        "Bravo",
        "Alpha",
        "Charlie",
        "Delta",
        "Echo",
    ]
    assert [paper.score for paper in ranked] == [7.5, 6.5, 5.5, 4.0, 3.0]
    assert [paper.score for paper in ranked] == sorted(
        (paper.score for paper in ranked), reverse=True
    )
    assert ranked[0].embedding_score == 5.0
    assert ranked[0].rerank_score == 10.0

    html = render_email(ranked)
    assert html.index("Bravo") < html.index("Alpha")
    assert "7.5" in html
    assert html.count('class="full-star"') > 0


def test_hybrid_low_raw_scores_do_not_become_ten(config, monkeypatch):
    candidates = [
        make_sample_paper(title="Target", url="https://example.test/target"),
        make_sample_paper(title="Other", url="https://example.test/other"),
    ]
    embedding = {candidates[0].url: 2.3, candidates[1].url: 2.0}
    cross = {candidates[0].url: 2.9, candidates[1].url: 2.0}

    monkeypatch.setattr(
        "zotero_arxiv_daily.reranker.hybrid._raw_embedding_scores",
        lambda reranker, papers, corpus: embedding,
    )
    monkeypatch.setattr(
        "zotero_arxiv_daily.reranker.hybrid._raw_rerank_scores",
        lambda reranker, papers, corpus: cross,
    )

    ranked = HybridReranker(config).rerank(candidates, make_sample_corpus())

    assert ranked[0].title == "Target"
    assert ranked[0].score == 2.6
    html = render_email(ranked)
    assert "2.6 (no match)" in html
    assert "embedding 2.3" in html
    assert "rerank 2.9" in html
