import feedparser
import re
from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from loguru import logger
from typing import Any
from time import sleep


@register_retriever("nature")
class NatureRetriever(BaseRetriever):
    """Retrieve latest papers from Nature Communications RSS feed.

    Configuration expects ``source.nature.feed_url`` — a single RSS URL.
    Example::

        source:
          nature:
            feed_url: "https://www.nature.com/ncomms.rss"
    """

    def __init__(self, config):
        super().__init__(config)
        feed_url = self.retriever_config.get("feed_url")
        if not feed_url:
            raise ValueError(
                "source.nature.feed_url must contain the Nature "
                "Communications RSS URL."
            )
        self.feed_url = feed_url.strip()

    # — BaseRetriever interface ——————————————————————————————————

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        logger.info(f"Fetching Nature RSS feed: {self.feed_url}")
        feed = feedparser.parse(self.feed_url)

        if feed.bozo and not feed.entries:
            logger.warning(
                f"Failed to parse Nature RSS feed ({self.feed_url}): "
                f"{feed.bozo_exception}"
            )
            return []

        entries = feed.entries
        if self.config.executor.debug:
            entries = entries[:10]

        logger.info(f"  -> {len(entries)} entries from Nature RSS")
        return list(entries)

    def convert_to_paper(self, raw_paper: dict[str, Any]) -> Paper | None:
        title = _strip_html(raw_paper.get("title", "")).strip()
        if not title:
            return None

        # Authors come as a list of {"name": "..."} dicts
        authors_raw = raw_paper.get("authors", [])
        authors = [a["name"].strip() for a in authors_raw if a.get("name")]

        # Abstract is embedded in the summary HTML after a journal metadata
        # prefix of the form:
        #   "Nature Communications, Published online: 01 June 2026; doi:XXX"
        abstract = _extract_nature_abstract(raw_paper.get("summary", ""))

        url = raw_paper.get("link", "")

        # Publication date from `updated` field (e.g. "2026-06-01")
        pub_date = raw_paper.get("updated", "")
        # Strip time portion if present
        pub_date = pub_date[:10] if pub_date else None

        journal = raw_paper.get("prism_publicationname", "Nature Communications")

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


# — helpers ——————————————————————————————————————————————————————

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from *text*."""
    return _HTML_TAG_RE.sub("", text)


_NATURE_ABSTRACT_PREFIX_RE = re.compile(
    r"^Nature\s+Communications,\s*Published\s+online:\s*[^;]+;\s*doi:\s*\S+\s*",
    re.IGNORECASE,
)


def _extract_nature_abstract(summary: str) -> str:
    """Extract the actual abstract from a Nature RSS summary field.

    The raw summary looks like::

        <p>Nature Communications, Published online: 01 June 2026;
        <a href="...">doi:10.1038/s41467-...</a></p>Actual abstract text...

    Returns the abstract text with HTML tags removed, or an empty string
    if no abstract could be extracted.
    """
    if not summary:
        return ""

    # Strip HTML tags (with a space so "</p>Insect" → " Insect")
    clean = re.sub(r"<[^>]+>", " ", summary)
    clean = re.sub(r"\s+", " ", clean).strip()

    # Remove the journal metadata prefix
    abstract = _NATURE_ABSTRACT_PREFIX_RE.sub("", clean).strip()

    # Also strip leading "doi:..." if the regex didn't fully catch it
    abstract = re.sub(r"^doi:\s*\S+\s*", "", abstract).strip()

    return abstract
