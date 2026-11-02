from types import SimpleNamespace

from langchain_core.documents import Document

from bankingsupportagent.rag import retriever
from bankingsupportagent.rag.ingest import document_title, split_pages


def page(text, number, source="05_schedule_of_charges_and_services.pdf"):
    return Document(page_content=text, metadata={"source": source, "page": number})


def test_document_title():
    assert document_title("03_debit_and_credit_card_terms.pdf") == "Debit and credit card terms"


def test_chunk_starts_with_document_and_section_label():
    chunks = split_pages([page("1. General\nIntro text.\n2. Fund Transfers\nUPI is free.", 1)])

    assert chunks[0].page_content.startswith("[Schedule of charges and services | 1. General]\n")
    assert chunks[0].metadata["section"] == "1. General"


def test_section_carries_over_to_the_next_page():
    chunks = split_pages([
        page("2. Fund Transfers\nUPI is free.", 1),
        page("NEFT is free as well.", 2),            # no heading on this page: still part of section 2
    ])

    assert chunks[1].metadata["section"] == "2. Fund Transfers"
    assert chunks[1].page_content.startswith("[Schedule of charges and services | 2. Fund Transfers]")


def test_section_resets_for_a_new_document():
    chunks = split_pages([
        page("2. Fund Transfers\nUPI is free.", 1),
        page("Intro without a heading.", 1, source="06_grievance_redressal_policy.pdf"),
    ])

    assert chunks[1].metadata["section"] == ""
    assert chunks[1].page_content.startswith("[Grievance redressal policy]\n")


def test_table_numbers_are_not_mistaken_for_headings():
    chunks = split_pages([page("3. ATM Transactions\n7 days to 45 days\n3.50%\n5 years (Tax Saver FD)", 1)])

    assert chunks[0].metadata["section"] == "3. ATM Transactions"


def test_retrieve_returns_chunks_in_reranker_order(monkeypatch):
    found = [Document(page_content=text, metadata={}) for text in ("loosely related", "exact answer", "unrelated")]
    monkeypatch.setattr(retriever, "get_vector_store", lambda: SimpleNamespace(similarity_search=lambda query, k: found))
    scores = {"loosely related": 0.2, "exact answer": 0.9, "unrelated": -3.0}
    monkeypatch.setattr(retriever, "get_reranker", lambda: SimpleNamespace(
        predict=lambda pairs: [scores[text] for _, text in pairs]))

    best = retriever.retrieve("question", k=2)

    assert [d.page_content for d in best] == ["exact answer", "loosely related"]
