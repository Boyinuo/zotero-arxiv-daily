import html
import re
from time import sleep, strftime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import feedparser
from loguru import logger

from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from ..metadata import extract_doi, normalize_abstract


@register_retriever("sage")
class SageRetriever(BaseRetriever):
    """Retrieve ahead-of-print papers from Sage Journals RSS feeds.

    ``source.sage.feed_urls`` accepts either full RSS URLs or bare Sage
    journal codes such as ``srb`` and ``ijr``.
    """

    @staticmethod
    def _normalize_feed_url(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith(("http://", "https://")):
            return raw

        journal_code = raw.strip("/")
        return (
            "https://journals.sagepub.com/action/showFeed"
            "?ui=0&mi=ehikzz&ai=2b4"
            f"&jc={quote(journal_code, safe='')}"
            "&type=axatoc&feed=rss"
        )

    def __init__(self, config):
        super().__init__(config)
        raw_urls = self.retriever_config.get("feed_urls", [])
        if not raw_urls:
            raise ValueError(
                "source.sage.feed_urls must contain at least one "
                "Sage journal code or RSS URL."
            )
        self.feed_urls = [self._normalize_feed_url(url) for url in raw_urls]

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        all_entries: list[dict[str, Any]] = []
        for url in self.feed_urls:
            logger.info(f"Fetching Sage Journals RSS feed: {url}")
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                logger.warning(
                    f"Failed to parse Sage Journals RSS feed ({url}): "
                    f"{feed.bozo_exception}"
                )
                continue

            entries = feed.entries[:10] if self.config.executor.debug else feed.entries
            feed_name = feed.feed.get("description", feed.feed.get("title", url))
            logger.info(f"  -> {len(entries)} entries from {feed_name}")
            all_entries.extend(entries)
            sleep(1)

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for entry in all_entries:
            identifier = (
                entry.get("prism_doi")
                or entry.get("dc_identifier")
                or entry.get("id")
                or entry.get("link")
            )
            if identifier and identifier in seen:
                continue
            if identifier:
                seen.add(identifier)
            unique.append(entry)
        return unique

    def convert_to_paper(self, raw_paper: dict[str, Any]) -> Paper | None:
        title = _strip_html(raw_paper.get("title", "")).strip()
        if not title:
            return None

        authors = _extract_authors(raw_paper)
        journal = raw_paper.get("prism_publicationname", "") or "Sage Journals"
        abstract = normalize_abstract(
            _extract_abstract(raw_paper.get("summary", ""), journal)
        )
        if not authors and not abstract:
            return None

        url = _canonical_article_url(
            raw_paper.get("prism_url", "") or raw_paper.get("link", "")
        )
        doi = extract_doi(
            raw_paper.get("prism_doi"),
            raw_paper.get("dc_identifier"),
            raw_paper.get("id"),
            url,
        )

        pub_date = raw_paper.get("updated", "") or raw_paper.get("published", "")
        pub_date = pub_date[:10] if pub_date else None
        if not pub_date:
            parsed_date = raw_paper.get("updated_parsed") or raw_paper.get(
                "published_parsed"
            )
            if parsed_date:
                pub_date = strftime("%Y-%m-%d", parsed_date)

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


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return html.unescape(_HTML_TAG_RE.sub("", text))


def _extract_authors(raw_paper: dict[str, Any]) -> list[str]:
    author_text = raw_paper.get("author", "")
    if not author_text:
        author_records = raw_paper.get("authors", [])
        author_text = ", ".join(
            record.get("name", "") for record in author_records if record.get("name")
        )

    author_text = _strip_html(author_text).strip()
    if not author_text:
        return []

    # Sage appends numbered affiliation text directly to the final author,
    # e.g. "Jane Doe1Department of Robotics, ...".  The first digit run
    # immediately followed by an institution name marks that boundary.
    author_text = re.split(r"\d+\s*(?=[A-Z])", author_text, maxsplit=1)[0]
    author_text = re.sub(r"\s+and\s+", ", ", author_text, flags=re.IGNORECASE)
    return [name.strip() for name in author_text.split(",") if name.strip()]


def _extract_abstract(summary: str, journal: str) -> str:
    if not summary:
        return ""

    clean = html.unescape(re.sub(r"<[^>]+>", " ", summary))
    clean = re.sub(r"\s+", " ", clean).strip()

    # Ahead-of-print feeds prefix every abstract with
    # "<Journal>, Ahead of Print.".  Prefer the exact journal name, then a
    # generic fallback so the parser also works when metadata is incomplete.
    if journal and journal != "Sage Journals":
        clean = re.sub(
            rf"^{re.escape(journal)}\s*,\s*Ahead of Print\.\s*",
            "",
            clean,
            count=1,
            flags=re.IGNORECASE,
        )
    clean = re.sub(
        r"^[^,]+,\s*Ahead of Print\.\s*",
        "",
        clean,
        count=1,
        flags=re.IGNORECASE,
    )
    return clean.strip()


def _canonical_article_url(url: str) -> str:
    """Drop Sage's tracking query parameters from a stable article URL."""
    if not url:
        return ""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
