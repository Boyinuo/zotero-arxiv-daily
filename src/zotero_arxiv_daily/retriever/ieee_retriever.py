import feedparser
import re
from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from loguru import logger
from typing import Any
from time import sleep


# — publication ID → journal abbreviation ——————————————————————————————

_JOURNAL_MAP: dict[str, str] = {
    "7083369": "RA-L",
    "8860": "TRO",
    "8856": "TASE",
    "3516": "TMECH",
    "100": "RAM",
    "6221037": "THMS",
    "6221036": "TCYB",
    "6221021": "TSMC",
    "41": "TIE",
    "6046": "TMM",
    "6221020": "JBHI",
}


def _pub_id_from_url(url: str) -> str | None:
    """Extract the numeric publication ID from an IEEE TOC RSS URL.

    >>> _pub_id_from_url("https://ieeexplore.ieee.org/rss/TOC7083369.XML")
    '7083369'
    """
    m = re.search(r"TOC(\d+)", url, re.IGNORECASE)
    return m.group(1) if m else None


@register_retriever("ieee")
class IEEERetriever(BaseRetriever):
    """Retrieve latest papers from IEEE Xplore journals via RSS feeds.

    Each IEEE journal publishes a Table-of-Contents (TOC) RSS feed at a URL of
    the form: ``https://ieeexplore.ieee.org/rss/TOC{publication_id}.XML``.

    Configuration expects ``source.ieee.feed_urls`` — a list of full RSS feed
    URLs (or plain publication IDs, which are auto-expanded to the canonical
    URL form).  Example config::

        source:
          ieee:
            feed_urls:
              - "https://ieeexplore.ieee.org/rss/TOC7083369.XML"   # RA-L
              - "https://ieeexplore.ieee.org/rss/TOC8860.XML"       # TRO
              - "8856"                                               # TASE (shorthand)

    Known IEEE publication IDs (robotics/automation/AI-related):

    ======  ===========================================
    ID       Journal
    ======  ===========================================
    8860     IEEE Transactions on Robotics (TRO)
    7083369  IEEE Robotics and Automation Letters (RA-L)
    8856     IEEE Transactions on Automation Science and Engineering (TASE)
    3516     IEEE/ASME Transactions on Mechatronics (TMECH)
    100      IEEE Robotics & Automation Magazine (RAM)
    6221037  IEEE Transactions on Human-Machine Systems
    6221036  IEEE Transactions on Cybernetics
    6221021  IEEE Transactions on Systems, Man, and Cybernetics: Systems
    41       IEEE Transactions on Industrial Electronics
    6046     IEEE Transactions on Multimedia
    6221020  IEEE Journal of Biomedical and Health Informatics
    ======  ===========================================
    """

    # — helpers ———————————————————————————————————————————————————

    @staticmethod
    def _normalize_feed_url(raw: str) -> str:
        """Accept either a full RSS URL or a bare publication ID."""
        raw = raw.strip()
        if raw.startswith("http"):
            return raw
        # Assume it's a numeric publication ID
        pub_id = raw.rstrip(".XML").rstrip(".xml")
        return f"https://ieeexplore.ieee.org/rss/TOC{pub_id}.XML"

    # — BaseRetriever interface ——————————————————————————————————

    def __init__(self, config):
        super().__init__(config)
        raw_urls = self.retriever_config.get("feed_urls", [])
        if not raw_urls:
            raise ValueError(
                "source.ieee.feed_urls must contain at least one "
                "IEEE RSS feed URL or publication ID."
            )
        self.feed_urls = [self._normalize_feed_url(u) for u in raw_urls]

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []
        for url in self.feed_urls:
            logger.info(f"Fetching IEEE RSS feed: {url}")
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                logger.warning(
                    f"Failed to parse RSS feed ({url}): "
                    f"{feed.bozo_exception}"
                )
                continue

            pub_id = _pub_id_from_url(url)
            journal = _JOURNAL_MAP.get(pub_id, "IEEE") if pub_id else "IEEE"

            logger.info(
                f"  -> {len(feed.entries)} entries from "
                f"{feed.feed.get('title', url)} ({journal})"
            )

            # Tag every entry with its source journal
            for entry in feed.entries:
                entry["_journal"] = journal

            if self.config.executor.debug:
                all_entries.extend(feed.entries[:10])
            else:
                all_entries.extend(feed.entries)

            sleep(1)  # be polite between feeds

        # Deduplicate by guid (a paper may appear in multiple feeds if
        # journals share content, e.g. early-access cross-posts).
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for e in all_entries:
            gid = e.get("guid", e.get("link", ""))
            if gid not in seen:
                seen.add(gid)
                unique.append(e)
        if len(unique) < len(all_entries):
            logger.info(
                f"Deduplicated {len(all_entries) - len(unique)} "
                f"duplicate entries."
            )
        return unique

    def convert_to_paper(self, raw_paper: dict[str, Any]) -> Paper | None:
        title = raw_paper.get("title", "").strip()
        if not title:
            return None

        # Authors are semicolon-separated in IEEE RSS
        author_str = raw_paper.get("authors", "")
        authors = [a.strip() for a in author_str.split(";") if a.strip()]

        # "description" in IEEE RSS is the abstract
        abstract = raw_paper.get("description", "")

        url = raw_paper.get("link", "")
        guid = raw_paper.get("guid", url)
        if isinstance(guid, str):
            url = guid  # prefer guid — it's the canonical document link
        elif url:
            url = url
        else:
            url = guid

        # Publication date from RSS (feedparser provides parsed struct_time)
        pub_date = None
        published_parsed = raw_paper.get("published_parsed")
        if published_parsed:
            from time import strftime
            pub_date = strftime("%Y-%m-%d", published_parsed)

        # IEEE does not expose direct PDF URLs in RSS feeds and the
        # papers are behind a paywall, so we leave pdf_url / full_text
        # as None, consistent with bioRxiv / medRxiv.

        journal = raw_paper.get("_journal", "IEEE")

        return Paper(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            url=url,
            pdf_url=None,
            full_text=None,
            pub_date=pub_date,
            journal=journal,
        )
