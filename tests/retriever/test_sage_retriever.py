from pathlib import Path

import feedparser
from omegaconf import OmegaConf

from zotero_arxiv_daily.retriever import get_retriever_cls
from zotero_arxiv_daily.retriever.sage_retriever import SageRetriever


def _config(*, debug: bool = False):
    return OmegaConf.create(
        {
            "source": {"sage": {"feed_urls": ["srb", "ijr"]}},
            "executor": {"debug": debug},
        }
    )


def test_sage_retriever_is_registered():
    assert get_retriever_cls("sage") is SageRetriever


def test_convert_realistic_sage_rss_entry():
    fixture = Path(__file__).with_name("sage_rss_example.xml")
    entry = feedparser.parse(fixture).entries[0]

    paper = SageRetriever(_config()).convert_to_paper(entry)

    assert paper is not None
    assert paper.source == "sage"
    assert paper.title == "A & B Soft Robot"
    assert paper.authors == ["Jane Doe", "John Smith"]
    assert paper.abstract == "A compact abstract about a soft robot."
    assert paper.url == "https://journals.sagepub.com/doi/abs/10.1177/example"
    assert paper.pub_date == "2026-09-10"
    assert paper.journal == "Soft Robotics"
    assert paper.pdf_url is None


def test_retrieve_deduplicates_entries_across_feeds(monkeypatch):
    duplicate = feedparser.FeedParserDict(
        {
            "title": "Duplicate paper",
            "link": "https://journals.sagepub.com/doi/abs/10.1177/example",
            "prism_doi": "10.1177/example",
        }
    )
    parsed = feedparser.FeedParserDict(
        {
            "bozo": False,
            "feed": feedparser.FeedParserDict({"title": "Sage Journals"}),
            "entries": [duplicate],
        }
    )
    monkeypatch.setattr(
        "zotero_arxiv_daily.retriever.sage_retriever.feedparser.parse",
        lambda _url: parsed,
    )
    monkeypatch.setattr(
        "zotero_arxiv_daily.retriever.sage_retriever.sleep", lambda _seconds: None
    )

    assert SageRetriever(_config())._retrieve_raw_papers() == [duplicate]


def test_missing_feed_urls_is_rejected():
    config = OmegaConf.create(
        {"source": {"sage": {"feed_urls": None}}, "executor": {"debug": False}}
    )

    try:
        SageRetriever(config)
    except ValueError as exc:
        assert "source.sage.feed_urls" in str(exc)
    else:
        raise AssertionError("Expected missing Sage feed URLs to be rejected")
