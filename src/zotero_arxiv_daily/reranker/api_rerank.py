"""Qwen3-Rerank cross-encoder — scores candidate papers against a user
interest query built from the Zotero corpus.

This is a *cross-encoder* (not a bi-encoder like the local or api_embedding
rerankers).  The model reads ``(query, document)`` pairs jointly and produces
relevance scores directly.  Because a single API call can handle up to 500
documents we can rerank all candidates in one round trip.
"""

from __future__ import annotations

import numpy as np
from openai import OpenAI

from .base import BaseReranker, register_reranker
from .interest_profile import corpus_by_priority, has_active_ratings
from ..protocol import Paper, CorpusPaper


@register_reranker("api_rerank")
class ApiRerankReranker(BaseReranker):
    """Reranker that calls the Qwen3-Rerank API (OpenAI-compatible /reranks)."""

    def get_similarity_score(self, s1: list[str], s2: list[str]) -> np.ndarray:
        """Not used — this reranker overrides ``rerank()`` directly with a cross-encoder."""
        raise NotImplementedError(
            "ApiRerankReranker uses rerank(), not get_similarity_score()"
        )

    def compute_scores(
        self, candidates: list[Paper], corpus: list[CorpusPaper]
    ) -> np.ndarray:
        cfg = self.config.reranker.api_rerank

        client = OpenAI(
            api_key=cfg.key,
            base_url=f"{cfg.base_url.rstrip('/')}",
        )

        query_max_tokens = cfg.get("query_max_tokens") or 30000
        query = self._build_interest_query(corpus, query_max_tokens, self.config)
        documents = [c.title + " " + c.abstract for c in candidates]

        body: dict = {
            "model": cfg.model,
            "query": query,
            "documents": documents,
            "top_n": len(candidates),
        }
        if cfg.instruct:
            body["instruct"] = cfg.instruct

        response = client.post("/reranks", body=body, cast_to=object)
        results = response["results"]

        # Build index → score map, preserving the original candidate order.
        score_map: dict[int, float] = {}
        for r in results:
            score_map[r["index"]] = r["relevance_score"]

        return np.array(
            [score_map.get(i, 0.0) * 10 for i in range(len(candidates))],
            dtype=float,
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_interest_query(
        corpus: list[CorpusPaper], max_tokens: int, config=None
    ) -> str:
        """Fuse the user's Zotero corpus into a representative query string.

        Rated corpora are ordered by combined rating/recency priority and
        annotated with their preference level. Unrated corpora retain the
        legacy newest-first representation.
        The query is capped at *max_tokens* to stay within model limits
        while carrying as much of the user's interest profile as possible.
        """
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4o")

        use_ratings = has_active_ratings(corpus, config)
        if use_ratings:
            corpus = corpus_by_priority(corpus, config)
            header = (
                "The following references describe the user's interests. "
                "A higher preference rating indicates stronger interest."
            )
            lines: list[str] = [header]
            tokens_used = len(enc.encode(header)) + 1
        else:
            # Preserve the legacy query exactly when the corpus is unrated.
            corpus = sorted(corpus, key=lambda x: x.added_date, reverse=True)
            lines = []
            tokens_used = 0

        for c in corpus:
            abstract_snip = c.abstract[:300]  # first 300 chars is enough signal
            if use_ratings:
                preference = (
                    f"{c.preference_rating}/5"
                    if c.preference_rating is not None
                    else "not rated"
                )
                line = f"[Preference: {preference}] {c.title}: {abstract_snip}"
            else:
                line = f"{c.title}: {abstract_snip}"
            line_tokens = len(enc.encode(line)) + 1  # +1 for the "\n\n" separator
            if tokens_used + line_tokens > max_tokens:
                break
            lines.append(line)
            tokens_used += line_tokens

        return "\n\n".join(lines)
