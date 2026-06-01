"""Tests for zotero_arxiv_daily.sent_tracker."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from zotero_arxiv_daily.protocol import Paper
from zotero_arxiv_daily.sent_tracker import SentTracker


# -- helpers ---------------------------------------------------------------


def _paper(url: str = "https://example.com/paper/1") -> Paper:
    return Paper(
        source="test",
        title="Test Paper",
        authors=["Author One"],
        abstract="Test abstract.",
        url=url,
    )


# -- basic load / save ----------------------------------------------------


def test_new_tracker_starts_empty():
    tracker = SentTracker(Path(tempfile.mkdtemp()) / "nonexistent.json")
    assert tracker.is_sent("https://example.com/paper/1") is False


def test_save_and_reload():
    d = Path(tempfile.mkdtemp())
    path = d / "sent.json"

    tracker = SentTracker(path)
    p = _paper()
    tracker.mark_sent([p])
    assert tracker.save() is True

    # reload — should remember the paper
    tracker2 = SentTracker(path)
    assert tracker2.is_sent(p.url) is True


def test_save_noop_when_no_new_papers():
    d = Path(tempfile.mkdtemp())
    path = d / "sent.json"

    tracker = SentTracker(path)
    assert tracker.save() is False  # nothing to persist


def test_corrupted_file_is_handled_gracefully():
    d = Path(tempfile.mkdtemp())
    path = d / "sent.json"
    path.write_text("not valid json {{")

    tracker = SentTracker(path)
    assert tracker.is_sent("anything") is False
    # should still be able to write a fresh file
    tracker.mark_sent([_paper("https://example.com/ok")])
    tracker.save()
    assert path.read_text().startswith("{")


# -- filter_new_papers ----------------------------------------------------


def test_filter_new_papers_removes_already_sent():
    d = Path(tempfile.mkdtemp())
    path = d / "sent.json"

    # First run — mark paper as sent
    t1 = SentTracker(path)
    t1.mark_sent([_paper("https://example.com/old")])
    t1.save()

    # Second run — same papers retrieved
    t2 = SentTracker(path)
    papers = [
        _paper("https://example.com/old"),    # already sent
        _paper("https://example.com/new"),    # new
    ]
    filtered = t2.filter_new_papers(papers)
    assert len(filtered) == 1
    assert filtered[0].url == "https://example.com/new"


def test_filter_keeps_papers_with_empty_url():
    tracker = SentTracker(Path(tempfile.mkdtemp()) / "nonexistent.json")
    p = _paper(url="")
    assert tracker.filter_new_papers([p]) == [p]


def test_filter_all_new_returns_all():
    tracker = SentTracker(Path(tempfile.mkdtemp()) / "nonexistent.json")
    papers = [_paper(f"https://example.com/{i}") for i in range(5)]
    assert tracker.filter_new_papers(papers) == papers


# -- mark_sent idempotency ------------------------------------------------


def test_mark_sent_twice_in_same_run_is_idempotent():
    d = Path(tempfile.mkdtemp())
    path = d / "sent.json"

    tracker = SentTracker(path)
    p = _paper()
    tracker.mark_sent([p])
    tracker.mark_sent([p])  # second call — should not duplicate
    tracker.save()

    data = json.loads(path.read_text())
    assert list(data.keys()).count(p.url) == 1
    assert p.url in data


# -- pruning --------------------------------------------------------------


def test_prune_removes_old_entries(monkeypatch):
    """Simulate entries that are older than max_age_days."""
    import json as _json

    d = Path(tempfile.mkdtemp())
    path = d / "sent.json"

    # Write a file with a mix of old and recent entries
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _json.dumps(
            {
                "https://example.com/old": "2020-01-01",
                "https://example.com/recent": "2026-06-01",
            }
        )
    )

    tracker = SentTracker(path, max_age_days=30)
    # need to mark something new to trigger save + prune
    tracker.mark_sent([_paper("https://example.com/brand-new")])
    tracker.save()

    data = _json.loads(path.read_text())
    urls = list(data.keys())
    assert "https://example.com/old" not in urls
    assert "https://example.com/recent" in urls
    assert "https://example.com/brand-new" in urls
