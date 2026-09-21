"""Tests for Zotero-specific metadata parsing."""

import pytest

from zotero_arxiv_daily.zotero_metadata import parse_preference_rating


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ("rate: 1", 1),
        ("Rate: 5", 5),
        ("DOI: 10.1234/example\n  rate : 3  \nPMID: 123", 3),
        ("rate: 0", None),
        ("rate: 6", None),
        ("rate: invalid", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_preference_rating(extra, expected):
    assert parse_preference_rating(extra) == expected
