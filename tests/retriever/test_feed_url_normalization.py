"""Tests for consistent short-form journal feed configuration."""

from omegaconf import OmegaConf

from zotero_arxiv_daily.retriever.ieee_retriever import IEEERetriever
from zotero_arxiv_daily.retriever.iop_retriever import IOPRetriever
from zotero_arxiv_daily.retriever.nature_retriever import NatureRetriever
from zotero_arxiv_daily.retriever.science_retriever import ScienceRetriever


def _config(source_name: str, source_config: dict):
    return OmegaConf.create(
        {
            "source": {source_name: source_config},
            "executor": {"debug": False},
        }
    )


def test_all_journal_sources_accept_short_feed_identifiers():
    ieee = IEEERetriever(_config("ieee", {"feed_urls": ["7083369"]}))
    nature = NatureRetriever(_config("nature", {"feed_urls": ["ncomms"]}))
    science = ScienceRetriever(
        _config("science", {"feed_urls": ["scirobotics", "sciadv"]})
    )
    iop = IOPRetriever(_config("iop", {"feed_urls": ["1748-3190"]}))

    assert ieee.feed_urls == ["https://ieeexplore.ieee.org/rss/TOC7083369.XML"]
    assert nature.feed_urls == ["https://www.nature.com/ncomms.rss"]
    assert science.feed_urls == [
        "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=scirobotics",
        "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",
    ]
    assert iop.feed_urls == ["https://iopscience.iop.org/journal/rss/1748-3190"]


def test_full_feed_urls_remain_supported():
    nature_url = "https://www.nature.com/ncomms.rss"
    science_url = (
        "https://www.science.org/action/showFeed"
        "?type=etoc&feed=rss&jc=scirobotics"
    )

    nature = NatureRetriever(_config("nature", {"feed_urls": [nature_url]}))
    science = ScienceRetriever(_config("science", {"feed_urls": [science_url]}))

    assert nature.feed_urls == [nature_url]
    assert science.feed_urls == [science_url]


def test_legacy_nature_feed_url_remains_supported():
    nature_url = "https://www.nature.com/ncomms.rss"
    retriever = NatureRetriever(_config("nature", {"feed_url": nature_url}))
    assert retriever.feed_urls == [nature_url]
