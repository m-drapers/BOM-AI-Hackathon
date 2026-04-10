"""Chunking + embedding pipeline for kanker.nl content and publications.

Creates two ChromaDB collections:
  - "kanker_nl"     -- kanker.nl patient information pages
  - "publications"  -- PDF reports and scientific papers

Run directly:
    cd backend && uv run python -m ingestion.vectorize
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import chromadb

# ---- Configuration ----

BACKEND_DIR = Path(__file__).resolve().parent.parent  # teams/team5/backend/
REPO_ROOT = BACKEND_DIR.parent.parent.parent  # /home/ralph/Projects/Hackathon-BOM-IKNL/
DATA_DIR = REPO_ROOT / "data"
KANKER_NL_JSON = DATA_DIR / "kanker_nl_pages_all.json"
SITEMAP_JSON = DATA_DIR / "sitemap.json"
CHROMADB_PATH = DATA_DIR / "chromadb"
REPORTS_DIR = DATA_DIR / "reports"
SCIENTIFIC_DIR = DATA_DIR / "scientific_publications"

CHUNK_SIZE = 500  # approximate tokens (we use words as proxy: ~1.3 tokens/word for Dutch)
CHUNK_OVERLAP = 50
WORDS_PER_CHUNK = 375  # ~500 tokens / 1.33 tokens per Dutch word
WORDS_OVERLAP = 38  # ~50 tokens

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

# Publication metadata lookup -- maps filename stems to metadata
PUBLICATION_META: dict[str, dict] = {
    "rapport_manvrouwverschillenbij-kanker_definitief2": {
        "source_type": "report",
        "title": "Man-vrouwverschillen bij kanker",
        "url": "https://iknl.nl/vrouw-man-verschillen-bij-kanker",
        "language": "nl",
        "topic": "Sekseverschillen in incidentie en uitkomsten",
    },
    "rapport_UItgezaaide-kanker_2025_cijfers-inzichten-en-uitdagingen": {
        "source_type": "report",
        "title": "Uitgezaaide kanker 2025",
        "url": "https://iknl.nl/uitgezaaide-kanker-2025",
        "language": "nl",
        "topic": "Cijfers, inzichten en uitdagingen bij uitgezaaide kanker",
    },
    "trendrapport_darmkanker_def": {
        "source_type": "report",
        "title": "Trendrapport darmkanker",
        "url": "https://iknl.nl/trendrapport-darmkanker",
        "language": "nl",
        "topic": "Langetermijntrends bij darmkanker",
    },
    "comorbidities_medication_use_and_overall_survival_in_eight_cancers": {
        "source_type": "publication",
        "title": "Comorbidities and survival in 8 cancers",
        "url": "https://doi.org/10.1016/S1470-2045(22)00734-X",
        "language": "en",
        "topic": "Impact of comorbid conditions on cancer survival (The Lancet)",
    },
    "head_and_neck_cancers_survival_in_europe_taiwan_and_japan": {
        "source_type": "publication",
        "title": "Head and neck cancers survival in Europe, Taiwan and Japan",
        "url": "https://doi.org/10.1016/S1470-2045(23)00588-X",
        "language": "en",
        "topic": "International comparison of head and neck cancer survival",
    },
    "ovarian_cancer_recurrence_prediction": {
        "source_type": "publication",
        "title": "Ovarian cancer recurrence prediction",
        "url": "https://doi.org/10.1016/j.ygyno.2023.01.029",
        "language": "en",
        "topic": "ML model for ovarian cancer outcomes (ESMO)",
    },
    "trends_and_variations_in_the_treatment_of_stage_I_III_non_small_cell_lung_cancer": {
        "source_type": "publication",
        "title": "Trends in treatment of stage I-III NSCLC",
        "url": "https://doi.org/10.1016/j.lungcan.2023.107356",
        "language": "en",
        "topic": "Treatment trends for non-small cell lung cancer",
    },
    "trends_and_variations_in_the_treatment_of_stage_I_III_small_cell_lung_cancer": {
        "source_type": "publication",
        "title": "Trends in treatment of stage I-III SCLC",
        "url": "https://doi.org/10.1016/j.lungcan.2023.107281",
        "language": "en",
        "topic": "Treatment trends for small cell lung cancer",
    },
}


def chunk_text(text: str, words_per_chunk: int = WORDS_PER_CHUNK, overlap: int = WORDS_OVERLAP) -> list[str]:
    """Split text into overlapping chunks of approximately `words_per_chunk` words.

    Uses word boundaries to avoid splitting mid-sentence where possible.
    Falls back to a simple word-count split -- good enough for a hackathon.
    """
    words = text.split()
    if len(words) <= words_per_chunk:
        return [text.strip()] if text.strip() else []

    chunks = []
    start = 0
    while start < len(words):
        end = start + words_per_chunk
        chunk_words = words[start:end]
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)
        start += words_per_chunk - overlap

    return chunks


def chunk_markdown(
    text: str,
    words_per_chunk: int = WORDS_PER_CHUNK,
    overlap: int = WORDS_OVERLAP,
) -> list[tuple[str, str]]:
    """Split Markdown into chunks respecting heading boundaries.

    Returns a list of (chunk_text, section_title) tuples.
    Long sections are sub-split by word count. Short consecutive sections
    are merged up to words_per_chunk.
    """
    sections: list[tuple[str, str]] = []
    parts = re.split(r"(?=^#{1,3}\s)", text, flags=re.MULTILINE)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        heading_match = re.match(r"^#{1,3}\s+(.*)", part)
        title = heading_match.group(1).strip() if heading_match else ""
        sections.append((part, title))

    if not sections:
        plain_chunks = chunk_text(text, words_per_chunk, overlap)
        return [(c, "") for c in plain_chunks]

    result: list[tuple[str, str]] = []
    buffer_text = ""
    buffer_title = ""

    for section_text, title in sections:
        section_words = len(section_text.split())

        if section_words > words_per_chunk:
            if buffer_text.strip():
                result.append((buffer_text.strip(), buffer_title))
                buffer_text = ""
                buffer_title = ""
            sub_chunks = chunk_text(section_text, words_per_chunk, overlap)
            for chunk in sub_chunks:
                result.append((chunk, title))
        else:
            combined_words = len(buffer_text.split()) + section_words
            if combined_words <= words_per_chunk:
                if not buffer_text:
                    buffer_title = title
                buffer_text += "\n\n" + section_text if buffer_text else section_text
            else:
                if buffer_text.strip():
                    result.append((buffer_text.strip(), buffer_title))
                buffer_text = section_text
                buffer_title = title

    if buffer_text.strip():
        result.append((buffer_text.strip(), buffer_title))

    return result


def extract_pdf_markdown(pdf_path: Path, converter=None) -> str:
    """Convert a PDF to Markdown using Docling, preserving tables and headings."""
    if converter is None:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    return result.document.export_to_markdown()


def get_embedding_function():
    """Create a ChromaDB-compatible embedding function using sentence-transformers."""
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
    )


def ingest_kanker_nl(client: chromadb.ClientAPI, ef):
    """Ingest kanker.nl pages into the 'kanker_nl' ChromaDB collection."""
    print("\n=== Ingesting kanker.nl content ===")

    # Load sitemap for metadata
    if not SITEMAP_JSON.exists():
        print(f"ERROR: {SITEMAP_JSON} not found. Run sitemap_builder.py first.")
        sys.exit(1)

    with open(SITEMAP_JSON, "r", encoding="utf-8") as f:
        sitemap: list[dict] = json.load(f)

    # Build URL -> metadata lookup
    url_meta = {entry["url"]: entry for entry in sitemap}

    # Load the full page content
    with open(KANKER_NL_JSON, "r", encoding="utf-8") as f:
        pages: dict[str, dict] = json.load(f)

    # Create or get collection
    collection = client.get_or_create_collection(
        name="kanker_nl",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Check if already populated
    existing = collection.count()
    if existing > 0:
        print(f"  Collection already has {existing} chunks. Deleting and re-creating...")
        client.delete_collection("kanker_nl")
        collection = client.create_collection(
            name="kanker_nl",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    all_ids = []
    all_documents = []
    all_metadatas = []
    skipped = 0
    seen_urls: set[str] = set()  # Track processed normalized URLs to avoid dupes

    for url, page in pages.items():
        text = page.get("text", "")
        if not text.strip() or "Error 503" in text[:200]:
            skipped += 1
            continue

        # Normalize URL to match sitemap
        norm_url = url.strip().rstrip("/")
        if norm_url.startswith("https://kanker.nl/"):
            norm_url = norm_url.replace("https://kanker.nl/", "https://www.kanker.nl/", 1)

        # Skip if we already processed this normalized URL
        if norm_url in seen_urls:
            skipped += 1
            continue

        meta = url_meta.get(norm_url)
        if meta is None:
            # Page was deduped out of the sitemap -- skip
            skipped += 1
            continue

        seen_urls.add(norm_url)
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            doc_id = f"kanker_nl_{hashlib.md5(norm_url.encode()).hexdigest()[:12]}_{i}"
            all_ids.append(doc_id)
            all_documents.append(chunk)
            all_metadatas.append({
                "kankersoort": meta["kankersoort"],
                "section": meta["section"],
                "url": meta["url"],
                "title": meta["title"],
            })

    print(f"  Pages processed: {len(pages) - skipped}, skipped: {skipped}")
    print(f"  Total chunks: {len(all_documents)}")

    # ChromaDB has a batch limit of ~41666 -- add in batches of 500
    batch_size = 500
    for i in range(0, len(all_documents), batch_size):
        end = min(i + batch_size, len(all_documents))
        collection.add(
            ids=all_ids[i:end],
            documents=all_documents[i:end],
            metadatas=all_metadatas[i:end],
        )
        print(f"  Added batch {i // batch_size + 1}: chunks {i}-{end}")

    print(f"  Done. Collection 'kanker_nl' has {collection.count()} chunks.")


def ingest_publications(client: chromadb.ClientAPI, ef):
    """Ingest PDF reports and scientific publications into the 'publications' collection."""
    print("\n=== Ingesting publications ===")

    collection = client.get_or_create_collection(
        name="publications",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    existing = collection.count()
    if existing > 0:
        print(f"  Collection already has {existing} chunks. Deleting and re-creating...")
        client.delete_collection("publications")
        collection = client.create_collection(
            name="publications",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    all_ids = []
    all_documents = []
    all_metadatas = []

    # Process both directories
    pdf_dirs = []
    if REPORTS_DIR.exists():
        pdf_dirs.append(REPORTS_DIR)
    if SCIENTIFIC_DIR.exists():
        pdf_dirs.append(SCIENTIFIC_DIR)

    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()

    for pdf_dir in pdf_dirs:
        for pdf_path in sorted(pdf_dir.glob("*.pdf")):
            stem = pdf_path.stem
            meta = PUBLICATION_META.get(stem)
            if meta is None:
                print(f"  WARNING: No metadata for {pdf_path.name}, using defaults")
                meta = {
                    "source_type": "publication",
                    "title": stem.replace("_", " ").title(),
                    "url": "https://iknl.nl/onderzoek/publicaties",
                    "language": "en",
                    "topic": "Unknown",
                }

            print(f"  Extracting: {pdf_path.name} ({meta['title']})")
            md_text = extract_pdf_markdown(pdf_path, converter=converter)
            if not md_text.strip():
                print(f"    WARNING: No text extracted from {pdf_path.name}")
                continue

            chunks = chunk_markdown(md_text)
            print(f"    {len(chunks)} chunks from {len(md_text)} chars")

            for i, (chunk_text_content, section_title) in enumerate(chunks):
                doc_id = f"pub_{hashlib.md5(stem.encode()).hexdigest()[:12]}_{i}"
                all_ids.append(doc_id)
                all_documents.append(chunk_text_content)
                all_metadatas.append({
                    "source_type": meta["source_type"],
                    "title": meta["title"],
                    "url": meta["url"],
                    "language": meta["language"],
                    "topic": meta["topic"],
                    "section_title": section_title,
                })

    print(f"  Total publication chunks: {len(all_documents)}")

    batch_size = 500
    for i in range(0, len(all_documents), batch_size):
        end = min(i + batch_size, len(all_documents))
        collection.add(
            ids=all_ids[i:end],
            documents=all_documents[i:end],
            metadatas=all_metadatas[i:end],
        )
        print(f"  Added batch {i // batch_size + 1}: chunks {i}-{end}")

    print(f"  Done. Collection 'publications' has {collection.count()} chunks.")


def main():
    print(f"ChromaDB path: {CHROMADB_PATH}")
    print(f"Embedding model: {EMBEDDING_MODEL}")

    CHROMADB_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
    ef = get_embedding_function()

    ingest_kanker_nl(client, ef)
    ingest_publications(client, ef)

    # Summary
    print("\n=== Summary ===")
    for col_name in ["kanker_nl", "publications"]:
        try:
            col = client.get_collection(col_name, embedding_function=ef)
            print(f"  {col_name}: {col.count()} chunks")
        except Exception as e:
            print(f"  {col_name}: ERROR - {e}")


if __name__ == "__main__":
    main()
