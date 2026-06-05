from .base import BaseRetriever, register_retriever
import arxiv
from arxiv import Result as ArxivResult
from ..protocol import Paper
from ..utils import extract_markdown_from_pdf, extract_tex_code_from_tar
from tempfile import TemporaryDirectory
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
import random as _random

T = TypeVar("T")

DOWNLOAD_TIMEOUT = (10, 60)
PDF_EXTRACT_TIMEOUT = 180
TAR_EXTRACT_TIMEOUT = 180


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

    def _retrieve_raw_papers(self) -> list[ArxivResult]:
        # Disable the arxiv library's own retry — it uses fixed 3-10 s delays
        # which are far too short when arXiv is genuinely rate-limiting.
        # We handle all retries at our level with proper exponential backoff.
        client = arxiv.Client(num_retries=0, delay_seconds=3)
        query = '+'.join(self.config.source.arxiv.category)
        include_cross_list = self.config.source.arxiv.get("include_cross_list", False)
        # Get the latest paper from arxiv rss feed
        feed = feedparser.parse(f"https://rss.arxiv.org/atom/{query}")
        if 'Feed error for query' in feed.feed.title:
            raise Exception(f"Invalid ARXIV_QUERY: {query}.")
        raw_papers = []
        allowed_announce_types = {"new", "cross"} if include_cross_list else {"new"}
        all_paper_ids = [
            re.sub(r"v\d+$", "", i.id.removeprefix("oai:arXiv.org:"))
            for i in feed.entries
            if i.get("arxiv_announce_type", "new") in allowed_announce_types
        ]
        if self.config.executor.debug:
            all_paper_ids = all_paper_ids[:10]

        # Get full information of each paper from arxiv api
        bar = tqdm(total=len(all_paper_ids))
        max_batch_retries = 5
        base_batch_retry_delay = 60  # seconds — doubles each retry
        inter_batch_delay = 30       # seconds between consecutive batches
        retryable_statuses = {429, 503}

        for i in range(0, len(all_paper_ids), 20):
            search = arxiv.Search(id_list=all_paper_ids[i:i + 20])
            for attempt in range(max_batch_retries):
                try:
                    batch = list(client.results(search))
                    bar.update(len(batch))
                    raw_papers.extend(batch)
                    break
                except arxiv.HTTPError as exc:
                    if exc.status in retryable_statuses and attempt < max_batch_retries - 1:
                        # Exponential backoff with jitter (±15 s)
                        wait = base_batch_retry_delay * (2 ** attempt) + _random.uniform(0, 15)
                        logger.warning(
                            f"arXiv API {exc.status} on batch {i // 20}, "
                            f"retry {attempt + 1}/{max_batch_retries} in {wait:.0f}s"
                        )
                        sleep(wait)
                    else:
                        raise
                except requests.exceptions.ConnectionError as exc:
                    if attempt < max_batch_retries - 1:
                        wait = base_batch_retry_delay * (2 ** attempt) + _random.uniform(0, 15)
                        logger.warning(
                            f"arXiv API connection error on batch {i // 20}: {exc}, "
                            f"retry {attempt + 1}/{max_batch_retries} in {wait:.0f}s"
                        )
                        sleep(wait)
                    else:
                        raise
            if i + 20 < len(all_paper_ids):
                # Add jitter to inter-batch delay as well
                sleep(inter_batch_delay + _random.uniform(0, 10))
        bar.close()

        return raw_papers

    def convert_to_paper(self, raw_paper: ArxivResult) -> Paper:
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
