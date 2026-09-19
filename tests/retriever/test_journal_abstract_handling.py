"""Regression tests for journal RSS abstract handling."""

from zotero_arxiv_daily.retriever.ieee_retriever import IEEERetriever
from zotero_arxiv_daily.retriever.science_retriever import ScienceRetriever


def test_science_entry_retains_doi_for_metadata_enrichment():
    retriever = ScienceRetriever.__new__(ScienceRetriever)
    paper = retriever.convert_to_paper(
        {
            "title": "A Science paper",
            "dc_type": "Research Article",
            "authors": [{"name": "Ada Lovelace, Grace Hopper"}],
            "prism_doi": "10.1126/sciadv.example",
            "link": "https://www.science.org/doi/abs/10.1126/sciadv.example?af=R",
            "prism_publicationname": "Science Advances",
        }
    )

    assert paper is not None
    assert paper.abstract == ""
    assert paper.doi == "10.1126/sciadv.example"


def test_ieee_literal_null_abstract_is_not_treated_as_content():
    retriever = IEEERetriever.__new__(IEEERetriever)
    paper = retriever.convert_to_paper(
        {
            "title": "Force Dimension",
            "authors": "",
            "description": "null",
            "link": "https://ieeexplore.ieee.org/document/123",
        }
    )

    assert paper is None
