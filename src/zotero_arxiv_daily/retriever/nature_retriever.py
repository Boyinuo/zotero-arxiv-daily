import feedparser
import re
from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from ..metadata import extract_doi, normalize_abstract
from loguru import logger
from typing import Any
from time import sleep


@register_retriever("nature")
class NatureRetriever(BaseRetriever):
    """Retrieve latest papers from Nature journal RSS feeds.

    Configuration expects ``source.nature.feed_urls`` — a list of journal
    slugs or full RSS URLs.  The legacy singular ``feed_url`` key is still
    accepted for backward compatibility.
    Example::

        source:
          nature:
            feed_urls:
              - "ncomms"
    """

    @staticmethod
    def _normalize_feed_url(raw: str) -> str:
        """Accept either a full RSS URL or a bare Nature journal slug."""
        raw = raw.strip()
        if raw.startswith(("http://", "https://")):
            return raw
        slug = raw.removesuffix(".rss").strip("/")
        return f"https://www.nature.com/{slug}.rss"

    def __init__(self, config):
        super().__init__(config)
        raw_urls = self.retriever_config.get("feed_urls")
        if not raw_urls:
            legacy_url = self.retriever_config.get("feed_url")
            raw_urls = [legacy_url] if legacy_url else []
        if not raw_urls:
            raise ValueError(
                "source.nature.feed_urls must contain at least one "
                "Nature journal slug or RSS URL."
            )
        self.feed_urls = [self._normalize_feed_url(url) for url in raw_urls]

    # — BaseRetriever interface ——————————————————————————————————

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []
        for url in self.feed_urls:
            logger.info(f"Fetching Nature RSS feed: {url}")
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                logger.warning(
                    f"Failed to parse Nature RSS feed ({url}): "
                    f"{feed.bozo_exception}"
                )
                continue

            entries = feed.entries[:10] if self.config.executor.debug else feed.entries
            logger.info(f"  -> {len(entries)} entries from Nature RSS")
            all_entries.extend(entries)
            sleep(1)

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for entry in all_entries:
            identifier = entry.get("id", entry.get("link", ""))
            if identifier not in seen:
                seen.add(identifier)
                unique.append(entry)
        return unique

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
        abstract = normalize_abstract(
            _extract_nature_abstract(raw_paper.get("summary", ""))
        )

        url = raw_paper.get("link", "")
        doi = extract_doi(
            raw_paper.get("prism_doi"),
            raw_paper.get("dc_identifier"),
            raw_paper.get("id"),
            url,
        )

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
            doi=doi,
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
