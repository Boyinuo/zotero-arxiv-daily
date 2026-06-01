"""Tracks which papers have already been included in a daily email.

Prevents the same paper from being sent to the user on consecutive days.
This is especially important for sources like IEEE Xplore whose TOC RSS
feeds return the same issue for weeks at a time.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from .protocol import Paper


class SentTracker:
    """Persistent record of paper URLs that have been emailed.

    The backing file (``data/sent_papers.json``) is a simple JSON object
    mapping each paper URL to the ISO-format date it was first sent::

        {
          "https://ieeexplore.ieee.org/document/11513897": "2026-06-01",
          "https://arxiv.org/abs/2026.12345": "2026-06-01"
        }

    Entries older than *max_age_days* are pruned automatically on save
    to prevent the file from growing unboundedly.
    """

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def __init__(self, file_path: str | Path, max_age_days: int = 90) -> None:
        self._file_path = Path(file_path)
        self._max_age_days = max_age_days
        self._sent: dict[str, str] = {}  # url → sent_date
        self._new_in_this_run: set[str] = set()
        self._load()

    def is_sent(self, url: str) -> bool:
        """Return ``True`` if *url* was already mailed in a previous run."""
        return url in self._sent

    def filter_new_papers(self, papers: list[Paper]) -> list[Paper]:
        """Return only the papers whose ``url`` has not been seen before.

        Papers with an empty ``url`` are always kept (we cannot track them).
        """
        new: list[Paper] = []
        skipped = 0
        for p in papers:
            if p.url and self.is_sent(p.url):
                skipped += 1
            else:
                new.append(p)
        if skipped:
            logger.info(
                f"Deduplication: skipped {skipped} already-sent "
                f"paper{'s' if skipped > 1 else ''}"
            )
        return new

    def mark_sent(self, papers: list[Paper]) -> None:
        """Record every *paper* as sent (keyed by ``paper.url``).

        Safe to call multiple times for the same paper within one run —
        the file is only touched once on :meth:`save`.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        for p in papers:
            if p.url:
                self._sent[p.url] = today
                self._new_in_this_run.add(p.url)

    def save(self) -> bool:
        """Persist the sent-paper records to disk.

        Returns ``True`` if the file was actually written, ``False`` if
        nothing changed since the last save (no-op).
        """
        if not self._new_in_this_run:
            return False

        self._prune_old_entries()

        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as fh:
            json.dump(self._sent, fh, ensure_ascii=False, indent=2)

        logger.info(
            f"Saved {len(self._sent)} sent-paper record(s) to "
            f"{self._file_path}"
        )
        self._new_in_this_run.clear()
        return True

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load existing records from disk (best-effort)."""
        if not self._file_path.exists():
            logger.info(
                f"No sent-papers file at {self._file_path} — "
                f"starting fresh (first run?)"
            )
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as fh:
                self._sent = json.load(fh)
            logger.info(
                f"Loaded {len(self._sent)} sent-paper record(s) from "
                f"{self._file_path}"
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                f"Failed to load {self._file_path}: {exc}. "
                f"Starting with an empty record."
            )
            self._sent = {}

    def _prune_old_entries(self) -> None:
        """Remove records older than ``_max_age_days``.

        A sliding window keeps the file from growing indefinitely while
        still preventing re-sends within the current publishing cycle.
        """
        if self._max_age_days <= 0:
            return

        cutoff = (datetime.now() - timedelta(days=self._max_age_days)).strftime(
            "%Y-%m-%d"
        )
        old_count = len(self._sent)
        self._sent = {
            u: d for u, d in self._sent.items() if d >= cutoff
        }
        removed = old_count - len(self._sent)
        if removed:
            logger.info(
                f"Pruned {removed} record(s) older than "
                f"{self._max_age_days} day(s)"
            )


# ------------------------------------------------------------------
# factory helper — resolves the default path relative to the
# *original* working directory (before Hydra changes it).
# ------------------------------------------------------------------


def sent_tracker_for_project(
    max_age_days: int = 90,
) -> SentTracker:
    """Create a ``SentTracker`` backed by ``data/sent_papers.json`` in
    the project root.

    Uses ``hydra.utils.get_original_cwd()`` so the path stays correct
    even when Hydra switches to an output sub-directory.
    """
    try:
        from hydra.utils import get_original_cwd

        root = get_original_cwd()
    except Exception:  # hydra may not be initialised (e.g. during tests)
        root = os.getcwd()

    path = Path(root) / "data" / "sent_papers.json"
    return SentTracker(path, max_age_days=max_age_days)
