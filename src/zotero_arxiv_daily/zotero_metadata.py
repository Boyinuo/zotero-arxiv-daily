"""Helpers for metadata stored in Zotero's ``extra`` field."""

from __future__ import annotations

import re


_RATE_PATTERN = re.compile(r"^\s*rate\s*:\s*([0-9]+)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_preference_rating(extra: str | None) -> int | None:
    """Return a Zotero Style ``rate`` value from an item's Extra field.

    Zotero Style stores its rating as a line such as ``rate: 4``. A cleared
    rating may be represented by ``rate: 0``; missing, cleared, and malformed
    values are all treated as unrated.
    """

    match = _RATE_PATTERN.search(extra or "")
    if not match:
        return None

    rating = int(match.group(1))
    return rating if 1 <= rating <= 5 else None
