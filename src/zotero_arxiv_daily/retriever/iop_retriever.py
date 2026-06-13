import feedparser
from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from loguru import logger
from typing import Any
from time import sleep, strftime


@register_retriever("iop")
class IOPRetriever(BaseRetriever):
    """Retriever for IOPscience journals via RSS feeds.

    Accepts ISSNs or full RSS feed URLs.
    Example RSS URL: https://iopscience.iop.org/journal/rss/1748-3190
    """

    @staticmethod
    def _normalize_feed_url(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith("http"):
            return raw
        return f"https://iopscience.iop.org/journal/rss/{raw}"

    def __init__(self, config):
        super().__init__(config)
        raw_urls = self.retriever_config.get("feed_urls", [])
        if not raw_urls:
            raise ValueError(
                "source.iop.feed_urls must contain at least one "
                "IOPscience RSS feed URL or ISSN."
            )
        self.feed_urls = [self._normalize_feed_url(u) for u in raw_urls]

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []
        for url in self.feed_urls:
            logger.info(f"Fetching IOPscience RSS feed: {url}")
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.warning(
                    f"Failed to parse IOPscience RSS feed ({url}): {feed.bozo_exception}"
                )
                continue
            journal = feed.feed.get("title", url)
            logger.info(f"  -> {len(feed.entries)} entries from {journal}")
            if self.config.executor.debug:
                all_entries.extend(feed.entries[:10])
            else:
                all_entries.extend(feed.entries)
            sleep(1)
        return all_entries

    def convert_to_paper(self, raw_paper: dict[str, Any]) -> Paper | None:
        title = raw_paper.get("title", "").strip()
        if not title:
            return None

        # Authors: feedparser maps dc:creator -> author (comma-separated, last pair may use "and")
        author_str = raw_paper.get("author", "")
        author_str = author_str.replace(" and ", ", ")
        authors = [a.strip() for a in author_str.split(",") if a.strip()]

        # Abstract: feedparser maps RSS description -> summary
        abstract = raw_paper.get("summary", "").strip()
        if not authors and not abstract:
            return None

        # URL
        url = raw_paper.get("link", "")

        # PDF URL: IOPscience provides PDF links in the feed (iop:pdf)
        pdf_url = raw_paper.get("iop_pdf", None)

        # Publication date: feedparser maps dc:date -> updated_parsed
        pub_date = None
        updated_parsed = raw_paper.get("updated_parsed")
        if updated_parsed:
            pub_date = strftime("%Y-%m-%d", updated_parsed)

        # Journal name
        journal = raw_paper.get("dc_source", "") or raw_paper.get(
            "prism_publicationname", "IOPscience"
        )

        return Paper(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            url=url,
            pdf_url=pdf_url,
            full_text=None,
            pub_date=pub_date,
            journal=journal,
        )
