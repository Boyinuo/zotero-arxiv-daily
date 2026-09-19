"""Tests for DOI extraction and abstract metadata enrichment."""

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily import metadata


def test_extract_doi_from_metadata_and_url():
    assert metadata.extract_doi("doi:10.1126/SCIADV.ABC123") == "10.1126/sciadv.abc123"
    assert (
        metadata.extract_doi("https://www.science.org/doi/abs/10.1126/scirobotics.xyz9?af=R")
        == "10.1126/scirobotics.xyz9"
    )


def test_normalize_abstract_removes_jats_and_rejects_null():
    assert metadata.normalize_abstract("<jats:p>A useful abstract.</jats:p>") == "A useful abstract."
    assert metadata.normalize_abstract(" null ") == ""
    assert not metadata.is_usable_abstract("None")


def test_fetch_abstract_prefers_crossref(monkeypatch):
    calls = []

    def fake_request(url, **kwargs):
        calls.append(url)
        return {"message": {"abstract": "<jats:p>Crossref abstract.</jats:p>"}}

    monkeypatch.setattr(metadata, "_request_json", fake_request)
    result = metadata.fetch_abstract_by_doi("10.1126/example")

    assert result == "Crossref abstract."
    assert len(calls) == 1
    assert "api.crossref.org" in calls[0]


def test_fetch_abstract_falls_back_to_openalex(monkeypatch):
    def fake_request(url, **kwargs):
        if "crossref" in url:
            return {"message": {}}
        return {
            "abstract_inverted_index": {
                "A": [0],
                "fallback": [1],
                "abstract.": [2],
            }
        }

    monkeypatch.setattr(metadata, "_request_json", fake_request)
    assert metadata.fetch_abstract_by_doi("10.1126/example") == "A fallback abstract."


def test_enrich_missing_abstracts_only_queries_doi_backed_candidates(monkeypatch):
    papers = [
        make_sample_paper(abstract="null", doi="10.1126/example"),
        make_sample_paper(abstract="Already present.", doi="10.1126/present"),
        make_sample_paper(abstract="", doi=None),
    ]
    calls = []

    def fake_fetch(doi, **kwargs):
        calls.append(doi)
        return "Recovered abstract."

    monkeypatch.setattr(metadata, "fetch_abstract_by_doi", fake_fetch)
    enriched = metadata.enrich_missing_abstracts(papers, request_delay=0)

    assert enriched == 1
    assert calls == ["10.1126/example"]
    assert papers[0].abstract == "Recovered abstract."
    assert papers[1].abstract == "Already present."
    assert papers[2].abstract == ""
