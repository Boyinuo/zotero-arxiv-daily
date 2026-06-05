from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from ..utils import extract_markdown_from_pdf, extract_tex_code_from_tar
from tempfile import TemporaryDirectory
from dataclasses import dataclass
from datetime import datetime
import feedparser
from tqdm import tqdm
import multiprocessing
import os
from queue import Empty
from time import sleep
from typing import Any, Callable, TypeVar
from loguru import logger
import requests
import re

T = TypeVar("T")

DOWNLOAD_TIMEOUT = (10, 60)
PDF_EXTRACT_TIMEOUT = 180
TAR_EXTRACT_TIMEOUT = 180


# ---------------------------------------------------------------------------
# Lightweight replacement for arxiv.Result, parsed from the RSS feed so we
# never hit the rate-limited export.arxiv.org API.  The RSS endpoint
# (rss.arxiv.org) is served from a separate caching layer and is not
# subject to the same aggressive rate limits.
# ---------------------------------------------------------------------------

_RSS_SUMMARY_RE = re.compile(
    r"^arXiv:\S+\s+Announce Type:\s+\S+\s*\n?\s*Abstract:\s*",
)


def _clean_rss_summary(raw: str) -> str:
    """Strip the arXiv-ID / announce-type prefix that RSS embeds in summaries.

    ``"arXiv:2508.13426v1 Announce Type: new\\nAbstract: The text..."``
    becomes ``"The text..."``.
    """
    return _RSS_SUMMARY_RE.sub("", raw, count=1).strip()


def _parse_rss_date(date_str: str) -> datetime | None:
    """Parse an RFC 3339 date string from an RSS entry."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


@dataclass
class _RssResult:
    """Lightweight mirror of ``arxiv.Result``, built from an RSS feed entry."""
    title: str
    summary: str
    authors: list[Any]       # list of objects with .name
    entry_id: str
    pdf_url: str
    published: datetime | None
    _source_url: str | None

    def source_url(self) -> str | None:
        return self._source_url


def _download_file(url: str, path: str) -> None:
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with open(path, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)


def _run_in_subprocess(
    result_queue: Any,
    func: Callable[..., T | None],
    args: tuple[Any, ...],
) -> None:
    try:
        result_queue.put(("ok", func(*args)))
    except Exception as exc:
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _run_with_hard_timeout(
    func: Callable[..., T | None],
    args: tuple[Any, ...],
    *,
    timeout: float,
    operation: str,
    paper_title: str,
) -> T | None:
    start_methods = multiprocessing.get_all_start_methods()
    context = multiprocessing.get_context("fork" if "fork" in start_methods else start_methods[0])
    result_queue = context.Queue()
    process = context.Process(target=_run_in_subprocess, args=(result_queue, func, args))
    process.start()

    try:
        status, payload = result_queue.get(timeout=timeout)
    except Empty:
        if process.is_alive():
            process.kill()
        process.join(5)
        result_queue.close()
        result_queue.join_thread()
        logger.warning(f"{operation} timed out for {paper_title} after {timeout} seconds")
        return None

    process.join(5)
    result_queue.close()
    result_queue.join_thread()

    if status == "ok":
        return payload

    logger.warning(f"{operation} failed for {paper_title}: {payload}")
    return None


def _extract_text_from_pdf_worker(pdf_url: str) -> str:
    with TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "paper.pdf")
        _download_file(pdf_url, path)
        return extract_markdown_from_pdf(path)


def _extract_text_from_html_worker(html_url: str) -> str | None:
    import trafilatura

    downloaded = trafilatura.fetch_url(html_url)
    if downloaded is None:
        raise ValueError(f"Failed to download HTML from {html_url}")
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text:
        raise ValueError(f"No text extracted from {html_url}")
    return text


def _extract_text_from_tar_worker(source_url: str, paper_id: str, paper_title: str | None = None) -> str | None:
    with TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "paper.tar.gz")
        _download_file(source_url, path)
        file_contents = extract_tex_code_from_tar(path, paper_id, paper_title=paper_title)
        if not file_contents or "all" not in file_contents:
            raise ValueError("Main tex file not found.")
        return file_contents["all"]


@register_retriever("arxiv")
class ArxivRetriever(BaseRetriever):
    def __init__(self, config):
        super().__init__(config)
        if self.config.source.arxiv.category is None:
            raise ValueError("category must be specified for arxiv.")

    def _retrieve_raw_papers(self) -> list[_RssResult]:
        """Parse the arXiv RSS feed directly — no API calls.

        The RSS endpoint (rss.arxiv.org) is a separate caching layer that is
        not subject to the aggressive rate limits of the API endpoint
        (export.arxiv.org).  Every RSS entry already contains title, summary
        (abstract), authors, publish date, and links — everything
        ``convert_to_paper`` needs.
        """
        query = "+".join(self.config.source.arxiv.category)
        include_cross_list = self.config.source.arxiv.get("include_cross_list", False)
        feed = feedparser.parse(f"https://rss.arxiv.org/atom/{query}")
        if "Feed error for query" in feed.feed.title:
            raise Exception(f"Invalid ARXIV_QUERY: {query}.")

        allowed_announce_types = {"new", "cross"} if include_cross_list else {"new"}
        from types import SimpleNamespace

        results: list[_RssResult] = []
        for entry in feed.entries:
            if entry.get("arxiv_announce_type", "new") not in allowed_announce_types:
                continue

            paper_id = re.sub(r"v\d+$", "", entry.id.removeprefix("oai:arXiv.org:"))
            authors = [
                SimpleNamespace(name=n.strip())
                for n in entry.get("dc_creator", "").split(",")
                if n.strip()
            ]
            entry_link = entry.get("link", "")
            entry_id = entry_link if entry_link else f"https://arxiv.org/abs/{paper_id}"

            results.append(
                _RssResult(
                    title=entry.title.strip(),
                    summary=_clean_rss_summary(entry.summary),
                    authors=authors,
                    entry_id=entry_id,
                    pdf_url=f"https://arxiv.org/pdf/{paper_id}",
                    _source_url=f"https://arxiv.org/e-print/{paper_id}",
                    published=_parse_rss_date(entry.get("published", "")),
                )
            )

        if self.config.executor.debug:
            results = results[:10]

        return results

    def convert_to_paper(self, raw_paper: _RssResult) -> Paper:
        """Lightweight conversion — full-text download is deferred to
        ``download_full_text()``, which should only be called for papers
        that survive dedup + ranking."""
        return Paper(
            source=self.name,
            title=raw_paper.title,
            authors=[a.name for a in raw_paper.authors],
            abstract=raw_paper.summary,
            url=raw_paper.entry_id,
            pdf_url=raw_paper.pdf_url,
            source_url=raw_paper.source_url(),
            full_text=None,
            pub_date=raw_paper.published.strftime("%Y-%m-%d") if raw_paper.published else None,
            journal="arXiv",
        )


def download_full_text(paper: Paper) -> str | None:
    """Download and extract full text for a single arXiv paper.

    Tries three sources in order: LaTeX tar → HTML → PDF.  The first
    successful extraction wins.  Returns the full text, or *None* if all
    three methods fail.
    """
    # 1) LaTeX source tarball
    if paper.source_url:
        ft = _run_with_hard_timeout(
            _extract_text_from_tar_worker,
            (paper.source_url, paper.url, paper.title),
            timeout=TAR_EXTRACT_TIMEOUT,
            operation="Tar extraction",
            paper_title=paper.title,
        )
        if ft:
            return ft

    # 2) arXiv HTML (not available for every paper)
    html_url = paper.url.replace("/abs/", "/html/")
    try:
        ft = _extract_text_from_html_worker(html_url)
        if ft:
            return ft
    except Exception as exc:
        logger.warning(f"HTML extraction failed for {paper.title}: {exc}")

    # 3) PDF fallback
    if paper.pdf_url:
        ft = _run_with_hard_timeout(
            _extract_text_from_pdf_worker,
            (paper.pdf_url,),
            timeout=PDF_EXTRACT_TIMEOUT,
            operation="PDF extraction",
            paper_title=paper.title,
        )
        if ft:
            return ft

    return None
