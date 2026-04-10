"""Tests for the docling-based ingestion pipeline."""

from pathlib import Path

import pytest

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
        intro = " ".join(["intro"] * 200)
        methods = " ".join(["methods"] * 200)
        results = " ".join(["results"] * 200)
        md = f"# Introduction\n\n{intro}\n\n## Methods\n\n{methods}\n\n## Results\n\n{results}"
        chunks = chunk_markdown(md, words_per_chunk=500, overlap=0)
        assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}"

    def test_preserves_heading_in_chunk(self):
        from ingestion.vectorize import chunk_markdown
        md = "# Introduction\n\nSome intro text.\n\n## Methods\n\nSome methods text."
        chunks = chunk_markdown(md, words_per_chunk=500, overlap=0)
        has_heading = any("#" in c[0] for c in chunks)
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
        assert all(isinstance(c, tuple) and len(c) == 2 for c in chunks)
        titles = [c[1] for c in chunks]
        assert any("Methods" in t for t in titles)
