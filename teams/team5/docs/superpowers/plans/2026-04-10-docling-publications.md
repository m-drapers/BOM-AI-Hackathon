# Docling Publications Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace PyMuPDF with Docling for PDF extraction in the publications ingestion pipeline, getting structure-aware Markdown with proper tables and section-based chunking.

**Architecture:** Drop-in replacement in `ingestion/vectorize.py`. Docling's `DocumentConverter` converts PDFs to Markdown (preserving tables, headings). A new `chunk_markdown()` splits on heading boundaries instead of raw word count. ChromaDB schema, connectors, and query layer are untouched.

**Tech Stack:** docling, chromadb, sentence-transformers

---

### Task 1: Update dependencies

**Files:**
- Modify: `teams/team5/backend/pyproject.toml:13` (replace pymupdf with docling)

- [ ] **Step 1: Replace pymupdf with docling in pyproject.toml**

In `pyproject.toml`, replace:
```
    "pymupdf>=1.24.0",
```
with:
```
    "docling>=2.0.0",
```

- [ ] **Step 2: Install dependencies**

Run: `cd /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend && uv sync`
Expected: docling and its dependencies install successfully. This will download ~500MB of ML models on first use.

- [ ] **Step 3: Commit**

```bash
git add teams/team5/backend/pyproject.toml teams/team5/backend/uv.lock
git commit -m "deps: replace pymupdf with docling for PDF extraction"
```

---

### Task 2: Write failing test for Markdown extraction

**Files:**
- Create: `teams/team5/backend/tests/test_ingestion/test_vectorize.py`

- [ ] **Step 1: Create test directory**

```bash
mkdir -p /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend/tests/test_ingestion
touch /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend/tests/test_ingestion/__init__.py
```

- [ ] **Step 2: Write test for extract_pdf_markdown**

Create `teams/team5/backend/tests/test_ingestion/test_vectorize.py`:

```python
"""Tests for the docling-based ingestion pipeline."""

from pathlib import Path

import pytest

# Use one of the actual pre-downloaded reports for integration testing
REPORTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "data" / "reports"
SAMPLE_PDF = REPORTS_DIR / "trendrapport_darmkanker_def.pdf"


class TestExtractPdfMarkdown:
    """Test Docling-based PDF extraction."""

    @pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="Sample PDF not available")
    def test_returns_non_empty_markdown(self):
        from ingestion.vectorize import extract_pdf_markdown

        result = extract_pdf_markdown(SAMPLE_PDF)
        assert isinstance(result, str)
        assert len(result) > 100, "Expected substantial Markdown output"

    @pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="Sample PDF not available")
    def test_contains_markdown_headings(self):
        from ingestion.vectorize import extract_pdf_markdown

        result = extract_pdf_markdown(SAMPLE_PDF)
        assert "#" in result, "Expected Markdown headings in output"


class TestChunkMarkdown:
    """Test section-aware Markdown chunking."""

    def test_splits_on_headings(self):
        from ingestion.vectorize import chunk_markdown

        md = "# Introduction\n\nSome intro text.\n\n## Methods\n\nSome methods text.\n\n## Results\n\nSome results."
        chunks = chunk_markdown(md, words_per_chunk=500, overlap=0)
        assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}"

    def test_preserves_heading_in_chunk(self):
        from ingestion.vectorize import chunk_markdown

        md = "# Introduction\n\nSome intro text.\n\n## Methods\n\nSome methods text."
        chunks = chunk_markdown(md, words_per_chunk=500, overlap=0)
        # At least one chunk should contain a heading marker
        has_heading = any("#" in c for c in chunks)
        assert has_heading, "Expected heading context preserved in chunks"

    def test_long_section_gets_split(self):
        from ingestion.vectorize import chunk_markdown

        long_text = " ".join(["word"] * 800)
        md = f"## Big Section\n\n{long_text}"
        chunks = chunk_markdown(md, words_per_chunk=375, overlap=38)
        assert len(chunks) >= 2, f"Expected long section to be split, got {len(chunks)} chunk(s)"

    def test_short_sections_merged(self):
        from ingestion.vectorize import chunk_markdown

        md = "## A\n\nShort.\n\n## B\n\nAlso short.\n\n## C\n\nTiny."
        chunks = chunk_markdown(md, words_per_chunk=375, overlap=0)
        assert len(chunks) <= 2, f"Expected short sections to merge, got {len(chunks)}"

    def test_returns_section_title_metadata(self):
        from ingestion.vectorize import chunk_markdown

        md = "## Methods\n\nSome methods text.\n\n## Results\n\nSome results."
        chunks = chunk_markdown(md, words_per_chunk=500, overlap=0)
        # chunk_markdown returns list of (chunk_text, section_title) tuples
        assert all(isinstance(c, tuple) and len(c) == 2 for c in chunks)
        titles = [c[1] for c in chunks]
        assert any("Methods" in t for t in titles)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend && uv run pytest tests/test_ingestion/test_vectorize.py -v`
Expected: FAIL — `extract_pdf_markdown` and `chunk_markdown` don't exist yet.

- [ ] **Step 4: Commit**

```bash
git add teams/team5/backend/tests/test_ingestion/
git commit -m "test: add failing tests for docling extraction and markdown chunking"
```

---

### Task 3: Implement extract_pdf_markdown

**Files:**
- Modify: `teams/team5/backend/ingestion/vectorize.py:114-121` (replace `extract_pdf_text`)

- [ ] **Step 1: Replace extract_pdf_text with extract_pdf_markdown**

In `ingestion/vectorize.py`, replace the existing `extract_pdf_text` function and its `import fitz` with:

Remove at top of file:
```python
import fitz  # PyMuPDF
```

Add at top of file:
```python
from docling.document_converter import DocumentConverter
```

Replace the function `extract_pdf_text` (lines 114-121) with:

```python
def extract_pdf_markdown(pdf_path: Path) -> str:
    """Convert a PDF to Markdown using Docling, preserving tables and headings."""
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    return result.document.export_to_markdown()
```

- [ ] **Step 2: Run extraction tests**

Run: `cd /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend && uv run pytest tests/test_ingestion/test_vectorize.py::TestExtractPdfMarkdown -v`
Expected: PASS (both tests)

- [ ] **Step 3: Commit**

```bash
git add teams/team5/backend/ingestion/vectorize.py
git commit -m "feat: replace PyMuPDF with Docling for PDF-to-Markdown extraction"
```

---

### Task 4: Implement chunk_markdown

**Files:**
- Modify: `teams/team5/backend/ingestion/vectorize.py` (add new function after `chunk_text`)

- [ ] **Step 1: Add chunk_markdown function**

Add this function after the existing `chunk_text` function (after line 111) in `ingestion/vectorize.py`:

```python
import re


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
    # Split on markdown headings (# or ##), keeping the heading with its content
    sections: list[tuple[str, str]] = []
    parts = re.split(r"(?=^#{1,3}\s)", text, flags=re.MULTILINE)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Extract heading title
        heading_match = re.match(r"^#{1,3}\s+(.*)", part)
        title = heading_match.group(1).strip() if heading_match else ""
        sections.append((part, title))

    if not sections:
        # No headings found — fall back to plain word-count chunking
        plain_chunks = chunk_text(text, words_per_chunk, overlap)
        return [(c, "") for c in plain_chunks]

    # Merge short sections, split long ones
    result: list[tuple[str, str]] = []
    buffer_text = ""
    buffer_title = ""

    for section_text, title in sections:
        section_words = len(section_text.split())

        if section_words > words_per_chunk:
            # Flush buffer first
            if buffer_text.strip():
                result.append((buffer_text.strip(), buffer_title))
                buffer_text = ""
                buffer_title = ""
            # Sub-split the long section by word count
            sub_chunks = chunk_text(section_text, words_per_chunk, overlap)
            for chunk in sub_chunks:
                result.append((chunk, title))
        else:
            # Try to merge with buffer
            combined_words = len(buffer_text.split()) + section_words
            if combined_words <= words_per_chunk:
                if not buffer_text:
                    buffer_title = title
                buffer_text += "\n\n" + section_text if buffer_text else section_text
            else:
                # Flush buffer, start new
                if buffer_text.strip():
                    result.append((buffer_text.strip(), buffer_title))
                buffer_text = section_text
                buffer_title = title

    # Flush remaining buffer
    if buffer_text.strip():
        result.append((buffer_text.strip(), buffer_title))

    return result
```

Note: move `import re` to the top of the file with the other imports.

- [ ] **Step 2: Run chunking tests**

Run: `cd /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend && uv run pytest tests/test_ingestion/test_vectorize.py::TestChunkMarkdown -v`
Expected: All 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add teams/team5/backend/ingestion/vectorize.py
git commit -m "feat: add section-aware Markdown chunking for publications"
```

---

### Task 5: Wire up ingest_publications to use new functions

**Files:**
- Modify: `teams/team5/backend/ingestion/vectorize.py:228-304` (`ingest_publications` function)

- [ ] **Step 1: Update ingest_publications**

In `ingest_publications()`, replace the extraction and chunking calls. Change:

```python
            print(f"  Extracting: {pdf_path.name} ({meta['title']})")
            text = extract_pdf_text(pdf_path)
            if not text.strip():
                print(f"    WARNING: No text extracted from {pdf_path.name}")
                continue

            chunks = chunk_text(text)
            print(f"    {len(chunks)} chunks from {len(text)} chars")

            for i, chunk in enumerate(chunks):
                doc_id = f"pub_{hashlib.md5(stem.encode()).hexdigest()[:12]}_{i}"
                all_ids.append(doc_id)
                all_documents.append(chunk)
                all_metadatas.append({
                    "source_type": meta["source_type"],
                    "title": meta["title"],
                    "language": meta["language"],
                    "topic": meta["topic"],
                })
```

to:

```python
            print(f"  Extracting: {pdf_path.name} ({meta['title']})")
            md_text = extract_pdf_markdown(pdf_path)
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
                    "language": meta["language"],
                    "topic": meta["topic"],
                    "section_title": section_title,
                })
```

- [ ] **Step 2: Run all tests**

Run: `cd /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend && uv run pytest tests/test_ingestion/ -v`
Expected: All tests PASS

- [ ] **Step 3: Smoke test the full pipeline**

Run: `cd /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend && uv run python -m ingestion.vectorize`
Expected: Both collections ingest successfully. Publications should show chunks with section metadata. Output like:
```
=== Ingesting publications ===
  Extracting: rapport_manvrouwverschillenbij-kanker_definitief2.pdf (Man-vrouwverschillen bij kanker)
    N chunks from M chars
  ...
  Done. Collection 'publications' has X chunks.
```

- [ ] **Step 4: Commit**

```bash
git add teams/team5/backend/ingestion/vectorize.py
git commit -m "feat: wire docling extraction into publications ingestion pipeline"
```

---

### Task 6: Clean up old PyMuPDF references

**Files:**
- Modify: `teams/team5/backend/ingestion/vectorize.py` (remove dead code)

- [ ] **Step 1: Remove old extract_pdf_text if still present**

If `extract_pdf_text` still exists in the file (it should have been replaced in Task 3), delete it. Also confirm `import fitz` is gone.

- [ ] **Step 2: Run full test suite**

Run: `cd /home/ralph/Projects/Hackathon-BOM-IKNL/teams/team5/backend && uv run pytest -v`
Expected: All tests pass, no import errors for fitz/pymupdf.

- [ ] **Step 3: Commit**

```bash
git add teams/team5/backend/ingestion/vectorize.py
git commit -m "chore: remove PyMuPDF remnants"
```
