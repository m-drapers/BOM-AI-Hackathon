# Docling Publications Pipeline — Design Spec

**Date**: 2026-04-10
**Status**: Approved

## Goal

Replace PyMuPDF with Docling for PDF extraction in the publications ingestion pipeline. Get structure-aware chunking (respecting headings/sections) and proper table extraction as Markdown.

## Scope

- Modify `ingestion/vectorize.py` — swap extraction and chunking for publications
- Update `pyproject.toml` — replace `pymupdf` with `docling`
- No changes to kanker.nl ingestion, connectors, query layer, or ChromaDB schema

## Design

### Dependencies

Replace `pymupdf>=1.24.0` with `docling` in `pyproject.toml`.

### PDF Extraction

New function `extract_pdf_markdown(pdf_path) -> str`:
- Uses `docling.document_converter.DocumentConverter`
- Converts PDF to Markdown via `result.document.export_to_markdown()`
- Tables become Markdown tables, headings are preserved as `#`/`##`/etc.

### Chunking

New function `chunk_markdown(text, words_per_chunk, overlap) -> list[str]`:
- Split on heading boundaries (`# ` or `## `)
- Each chunk gets prefixed with its section heading for retrieval context
- Sections exceeding `WORDS_PER_CHUNK` fall back to word-count splitting within the section
- Short consecutive sections are merged up to the chunk size limit

### Metadata

Add `section_title` field to each publication chunk's metadata. All existing metadata fields (title, source_type, language, topic) remain unchanged.

### Integration

`ingest_publications()` calls `extract_pdf_markdown()` and `chunk_markdown()` instead of `extract_pdf_text()` and `chunk_text()`. No other pipeline changes.

## What stays the same

- `kanker_nl` ingestion (JSON-based, not PDF)
- ChromaDB collections and embedding model (`multilingual-e5-small`)
- All connector and query code (`PublicationsConnector`, `KankerNLConnector`)
- Existing `chunk_text()` function (still used by kanker.nl ingestion)
