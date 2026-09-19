"""Helpers for DOI extraction and abstract metadata enrichment."""

from __future__ import annotations

import html
import json
import re
from time import sleep
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, unquote
from urllib.request import Request, urlopen

from loguru import logger

from .protocol import Paper


_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_INVALID_ABSTRACTS = frozenset({"null", "none", "n/a", "na", "undefined"})
_USER_AGENT = "zotero-arxiv-daily/1.0 (+https://github.com/TideDra/zotero-arxiv-daily)"


def extract_doi(*values: object) -> str | None:
    """Return the first DOI found in publisher metadata or an article URL."""
    for value in values:
        if value is None:
            continue
        match = _DOI_RE.search(unquote(str(value)))
        if match:
            return match.group(0).rstrip(".,;").lower()
    return None


def normalize_abstract(value: object) -> str:
    """Convert RSS/JATS abstract markup to normalized plain text."""
    if value is None:
        return ""
    text = html.unescape(_HTML_TAG_RE.sub(" ", str(value)))
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower() in _INVALID_ABSTRACTS:
        return ""
    return text


def is_usable_abstract(value: object) -> bool:
    return bool(normalize_abstract(value))


def _request_json(url: str, *, timeout: float = 15.0, retries: int = 2) -> Any | None:
    request = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt == retries - 1:
                logger.warning(f"Metadata request failed ({exc.code}) for {url}")
                return None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                logger.warning(f"Metadata request failed for {url}: {exc}")
                return None
        sleep(1.0 * (2**attempt))
    return None


def _reconstruct_openalex_abstract(inverted_index: object) -> str:
    if not isinstance(inverted_index, dict):
        return ""

    words_by_position: dict[int, str] = {}
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                words_by_position[position] = str(word)

    text = " ".join(words_by_position[position] for position in sorted(words_by_position))
    return normalize_abstract(text)


def fetch_abstract_by_doi(doi: str, *, contact_email: str | None = None) -> str | None:
    """Fetch an abstract from Crossref, then fall back to OpenAlex."""
    normalized_doi = extract_doi(doi)
    if not normalized_doi:
        return None

    crossref_url = f"https://api.crossref.org/works/{quote(normalized_doi, safe='')}"
    if contact_email and "@" in contact_email and "???" not in contact_email:
        crossref_url += "?" + urlencode({"mailto": contact_email})

    crossref = _request_json(crossref_url)
    if isinstance(crossref, dict):
        message = crossref.get("message", {})
        if isinstance(message, dict):
            abstract = normalize_abstract(message.get("abstract"))
            if abstract:
                return abstract

    openalex_url = f"https://api.openalex.org/works/doi:{quote(normalized_doi, safe='/')}"
    openalex = _request_json(openalex_url)
    if isinstance(openalex, dict):
        abstract = _reconstruct_openalex_abstract(openalex.get("abstract_inverted_index"))
        if abstract:
            return abstract

    return None


def enrich_missing_abstracts(
    papers: Iterable[Paper],
    *,
    contact_email: str | None = None,
    request_delay: float = 0.2,
) -> int:
    """Fill missing paper abstracts by DOI and return the number enriched."""
    candidates: list[Paper] = []
    for paper in papers:
        if is_usable_abstract(paper.abstract):
            continue
        paper.abstract = ""
        if paper.doi:
            candidates.append(paper)

    if not candidates:
        return 0

    logger.info(f"Fetching missing abstracts for {len(candidates)} DOI-backed papers...")
    cache: dict[str, str | None] = {}
    enriched = 0
    for index, paper in enumerate(candidates):
        doi = extract_doi(paper.doi)
        if not doi:
            continue
        if doi not in cache:
            cache[doi] = fetch_abstract_by_doi(doi, contact_email=contact_email)
            if request_delay > 0 and index < len(candidates) - 1:
                sleep(request_delay)
        if cache[doi]:
            paper.abstract = cache[doi] or ""
            enriched += 1
        else:
            logger.warning(f"No abstract metadata found for DOI {doi}")

    logger.info(f"Enriched abstracts for {enriched}/{len(candidates)} papers")
    return enriched
