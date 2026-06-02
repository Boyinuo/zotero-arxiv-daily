import feedparser
from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from loguru import logger
from typing import Any
from time import sleep


@register_retriever("science")
class ScienceRetriever(BaseRetriever):
    """Retrieve latest papers from Science journal RSS feeds (Science Robotics,
    Science Advances, etc.).

    Configuration expects ``source.science.feed_urls`` — a list of RSS URLs.
    Example::

        source:
          science:
            feed_urls:
              - "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=scirobotics"
              - "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv"

    .. note::

        The Science RSS feed does **not** include paper abstracts — only
        journal metadata.  Rankings will rely on title similarity alone
        and TLDR generation will fall back to the title-only prompt.
    """

    # Only these dc_type values represent full research papers
    _KEPT_TYPES = frozenset({"Research Article"})

    def __init__(self, config):
        super().__init__(config)
        raw_urls = self.retriever_config.get("feed_urls", [])
        if not raw_urls:
            raise ValueError(
                "source.science.feed_urls must contain at least one "
                "Science journal RSS URL."
            )
        self.feed_urls = [u.strip() for u in raw_urls]

    # — BaseRetriever interface ——————————————————————————————————

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []
        for url in self.feed_urls:
            logger.info(f"Fetching Science RSS feed: {url}")
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                logger.warning(
                    f"Failed to parse Science RSS feed ({url}): "
                    f"{feed.bozo_exception}"
                )
                continue

            journal = feed.feed.get("title", url)
            logger.info(
                f"  -> {len(feed.entries)} entries from {journal}"
            )

            if self.config.executor.debug:
                all_entries.extend(feed.entries[:10])
            else:
                all_entries.extend(feed.entries)

            sleep(1)  # be polite between feeds

        return all_entries

    def convert_to_paper(self, raw_paper: dict[str, Any]) -> Paper | None:
        title = raw_paper.get("title", "").strip()
        if not title:
            return None

        # Only keep full research articles
        dc_type = raw_paper.get("dc_type", "")
        if dc_type not in self._KEPT_TYPES:
            logger.debug(f"Skipping Science entry of type '{dc_type}': {title}")
            return None

        # Authors are in a single comma-separated string inside
        # authors[0]['name']
        authors_raw = raw_paper.get("authors", [])
        author_names: list[str] = []
        if authors_raw:
            name_str = authors_raw[0].get("name", "")
            author_names = [a.strip() for a in name_str.split(",") if a.strip()]

        # The Science RSS feed does *not* provide abstracts — summary
        # contains only journal metadata (volume, issue, date).
        abstract = ""

        url = raw_paper.get("link", "")

        # Publication date from prism_coverdate
        pub_date = raw_paper.get("prism_coverdate", "")
        pub_date = pub_date[:10] if pub_date else None

        journal = raw_paper.get("prism_publicationname", "Science")

        return Paper(
            source=self.name,
            title=title,
            authors=author_names,
            abstract=abstract,
            url=url,
            pdf_url=None,
            full_text=None,
            pub_date=pub_date,
            journal=journal,
        )
