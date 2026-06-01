"""Qwen3-Rerank cross-encoder — scores candidate papers against a user
interest query built from the Zotero corpus.

This is a *cross-encoder* (not a bi-encoder like the local or api_embedding
rerankers).  The model reads ``(query, document)`` pairs jointly and produces
relevance scores directly.  Because a single API call can handle up to 500
documents we can rerank all candidates in one round trip.
"""

from __future__ import annotations

from openai import OpenAI

from .base import BaseReranker, register_reranker
from ..protocol import Paper, CorpusPaper


@register_reranker("api_rerank")
class ApiRerankReranker(BaseReranker):
    """Reranker that calls the Qwen3-Rerank API (OpenAI-compatible /reranks)."""

    def rerank(
        self, candidates: list[Paper], corpus: list[CorpusPaper]
    ) -> list[Paper]:
        cfg = self.config.reranker.api_rerank

        client = OpenAI(
            api_key=cfg.key,
            base_url=f"{cfg.base_url.rstrip('/')}",
        )

        query_max_tokens = cfg.get("query_max_tokens") or 30000
        query = self._build_interest_query(corpus, query_max_tokens)
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
        results = response.results

        # Build index → score map, then assign scores
        score_map: dict[int, float] = {}
        for r in results:
            score_map[r.index] = r.relevance_score

        for i, c in enumerate(candidates):
            c.score = score_map.get(i, 0.0) * 10  # scale to ~0–10

        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_interest_query(corpus: list[CorpusPaper], max_tokens: int) -> str:
        """Fuse the user's Zotero corpus into a representative query string.

        More recently added papers are placed near the front so the
        cross-encoder's self-attention naturally weights them higher.
        The query is capped at *max_tokens* to stay within model limits
        while carrying as much of the user's interest profile as possible.
        """
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4o")

        corpus = sorted(corpus, key=lambda x: x.added_date, reverse=True)
        lines: list[str] = []
        tokens_used = 0

        for c in corpus:
            abstract_snip = c.abstract[:300]  # first 300 chars is enough signal
            line = f"{c.title}: {abstract_snip}"
            line_tokens = len(enc.encode(line)) + 1  # +1 for the "\n\n" separator
            if tokens_used + line_tokens > max_tokens:
                break
            lines.append(line)
            tokens_used += line_tokens

        return "\n\n".join(lines)
