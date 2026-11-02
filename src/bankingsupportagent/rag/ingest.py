from pathlib import Path

from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
import re

from bankingsupportagent.config import DOCS_DIR,CHROMA_DIR,COLLECTION_NAME,get_embeddings

CHUNK_SIZE=200
CHUNK_OVERLAP=40

FOOTER_PREFIX = "SecureBank Ltd. |"

# A numbered section title on its own line: "6. Non-maintenance of Minimum Balance", "4.1 Salary account conversion"
SECTION_HEADING = re.compile(r"^\d+(?:\.\d+)?\.?\s+[A-Z][^\n]{2,80}$", re.MULTILINE)

def word_count(text:str)->int:
    return len(text.split())


def load_pdfs():
    """Load every PDF in DOCS_DIR. Each page becomes one Document."""
    pages = []
    for path in sorted(DOCS_DIR.glob("*.pdf")):
        reader = PdfReader(path)
        for page_number, page in enumerate(reader.pages, start=1):
            pages.append(Document(
                page_content=clean_page_text(page.extract_text()),
                metadata={"source": path.name, "page": page_number},
            ))
    return pages

def clean_page_text(text:str) -> str:
    """Remove repeated page footers and page numbers from extracted text"""
    kept = []
    for line in text.splitlines():
        if line.startswith(FOOTER_PREFIX):
            continue
        if re.fullmatch(r"Page \d+",line.strip()):
            continue
        kept.append(line)
    return "\n".join(kept)


def document_title(filename: str) -> str:
    """'03_debit_and_credit_card_terms.pdf' -> 'Debit and credit card terms'"""
    words = Path(filename).stem.split("_")[1:]
    return " ".join(words).capitalize()


def split_pages(pages):
    """Cut pages into overlapping chunks of about CHUNK_SIZE words.

    A table row or a short paragraph on its own often says nothing about what it belongs to ("Rs. 1,000"
    of what?). So every chunk starts with a label: the document title and the section heading it sits under.
    The label is searched and shown to the LLM together with the text.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size = CHUNK_SIZE,
        chunk_overlap = CHUNK_OVERLAP,
        length_function = word_count,
        add_start_index = True,
    )
    chunks = []
    heading = ""
    for page in pages:
        if page.metadata["page"] == 1:
            heading = ""            # a new document starts
        found = [(m.start(), m.group().strip()) for m in SECTION_HEADING.finditer(page.page_content)]
        for chunk in splitter.split_documents([page]):
            start = chunk.metadata["start_index"]
            section = next((text for position, text in reversed(found) if position <= start), heading)
            label = " | ".join(part for part in (document_title(chunk.metadata["source"]), section) if part)
            chunk.metadata["section"] = section
            chunk.page_content = f"[{label}]\n{chunk.page_content}"
            chunks.append(chunk)
        if found:
            heading = found[-1][1]
    return chunks


def build_vector_store():
    """Load, split, embed and save all chunks in Chroma (rebuilds from scratch)"""
    pages = load_pdfs()
    chunks = split_pages(pages)

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR)
    )
    vector_store.reset_collection()
    vector_store.add_documents(chunks)

    print(f"Loaded {len(pages)} pages -> {len(chunks)} chunks -> saved to {CHROMA_DIR}")


if __name__ == "__main__":
    build_vector_store()