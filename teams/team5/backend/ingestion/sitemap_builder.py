"""Build a structured sitemap from the pre-crawled kanker.nl JSON.

Reads data/kanker_nl_pages_all.json (2,816 pages, 87 cancer types)
and produces data/sitemap.json with cleaned, deduplicated entries
containing kankersoort, section, url, title, and text_length metadata.

Run directly:
    cd backend && uv run python -m ingestion.sitemap_builder
"""

import json
import sys
from pathlib import Path

# ---- Configuration ----

# Resolve paths relative to the backend/ directory
BACKEND_DIR = Path(__file__).resolve().parent.parent  # teams/team5/backend/
REPO_ROOT = BACKEND_DIR.parent.parent.parent  # /home/ralph/Projects/Hackathon-BOM-IKNL/
DATA_DIR = REPO_ROOT / "data"
INPUT_PATH = DATA_DIR / "kanker_nl_pages_all.json"
OUTPUT_PATH = DATA_DIR / "sitemap.json"

CANONICAL_PREFIX = "https://www.kanker.nl/"

# The six canonical sections on kanker.nl. Anything else is mapped to one
# of these, or falls into "overig" if no match.
CANONICAL_SECTIONS = {
    "algemeen",
    "diagnose",
    "onderzoeken",
    "behandelingen",
    "gevolgen",
    "na-de-uitslag",
}

# Section name aliases found in the crawled data.  Each maps to one of the
# six canonical sections above.
SECTION_ALIAS_MAP: dict[str, str] = {
    # behandelingen variants
    "behandeling": "behandelingen",
    "behandeling-en-bijwerkingen": "behandelingen",
    "behandeling-van-borstkanker": "behandelingen",
    "behandeling-van-kwaadaardige-trofoblastziekten": "behandelingen",
    "behandelingen-bij-baarmoederhalskanker": "behandelingen",
    "behandelingen-bij-galwegkanker": "behandelingen",
    # onderzoeken variants
    "onderzoek": "onderzoeken",
    "onderzoek-en-diagnose": "onderzoeken",
    "onderzoeken-bij-zaadbalkanker": "onderzoeken",
    "onderzoeken-bij-borstkanker": "onderzoeken",
    # diagnose variants
    "de-diagnose-melanoom": "diagnose",
    "de-diagnose-borstkanker": "diagnose",
    "de-diagnose-baarmoederhalskanker": "diagnose",
    "de-diagnose-peniskanker": "diagnose",
    "de-diagnose-maagkanker": "diagnose",
    "de-diagnose-anuskanker": "diagnose",
    "diagnose-eierstokkanker": "diagnose",
    "de-uitslag": "diagnose",
    # na-de-uitslag variants
    "na-de-uitslag-baarmoederhalskanker": "na-de-uitslag",
    "na-de-uitslag-leukemie": "na-de-uitslag",
    "na-de-uitslag-leverkanker": "na-de-uitslag",
    "na-de-uitslag-merkelcelcarcinoom": "na-de-uitslag",
    "na-de-uitslag-oogkanker": "na-de-uitslag",
    "na-de-uitslag-primaire-tumor-onbekend": "na-de-uitslag",
    "na-de-uitslag-schaamlipkanker": "na-de-uitslag",
    "na-de-uitslag-vaginakanker": "na-de-uitslag",
    "na-de-diagnose-net": "na-de-uitslag",
    "leven-met-een-huidlymfoom": "na-de-uitslag",
    # gevolgen - no aliases found in the data so far
}

# Kankersoort slug normalization: old slug -> canonical slug.
# The crawled data contains pages under both the old and new name for
# two cancer types.  We keep the longer (newer) canonical slug and
# rewrite the old one.
KANKERSOORT_CANONICAL_MAP: dict[str, str] = {
    "botkanker": "botkanker-botsarcoom",
    "wekedelentumoren": "wekedelentumoren-wekedelensarcomen",
}


def normalize_url(url: str) -> str:
    """Normalize a URL to the canonical https://www.kanker.nl/ prefix
    and strip trailing slashes."""
    url = url.strip().rstrip("/")
    if url.startswith("https://kanker.nl/"):
        url = url.replace("https://kanker.nl/", CANONICAL_PREFIX, 1)
    return url


def parse_url_parts(url: str) -> tuple[str, str, str]:
    """Extract (kankersoort, section, page_slug) from a normalized kanker.nl URL.

    Returns ("", "", slug) for URLs that don't match the expected pattern.
    """
    path = url.replace(CANONICAL_PREFIX + "kankersoorten/", "")
    parts = path.split("/")

    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], ""
    elif len(parts) == 1:
        return parts[0], "", ""
    return "", "", ""


def extract_title(text: str) -> str:
    """Extract the page title from the first non-empty line of the text."""
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("Deze informatie"):
            return line[:200]
    return "Onbekend"


def build_sitemap() -> list[dict]:
    """Load the crawled JSON, clean, deduplicate, and return sitemap entries."""
    print(f"Loading {INPUT_PATH} ...")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        raw: dict[str, dict] = json.load(f)
    print(f"  Loaded {len(raw)} pages")

    # --- Pass 1: Normalize URLs, skip error pages, build candidate list ---
    candidates: dict[str, dict] = {}  # normalized_url -> entry
    skipped_errors = 0
    skipped_dupes = 0

    for url, page in raw.items():
        text = page.get("text", "")

        # Skip 503 error pages
        if "Error 503" in text[:200] or "Backend fetch failed" in text[:200]:
            skipped_errors += 1
            continue

        # Skip very short pages (likely broken)
        if len(text.strip()) < 30:
            skipped_errors += 1
            continue

        norm_url = normalize_url(url)

        # Deduplicate: keep the version with the most content
        if norm_url in candidates:
            skipped_dupes += 1
            if len(text) > len(candidates[norm_url]["text"]):
                candidates[norm_url]["text"] = text
            continue

        kankersoort_raw, section_raw, _ = parse_url_parts(norm_url)

        # Normalize kankersoort slug
        kankersoort = KANKERSOORT_CANONICAL_MAP.get(kankersoort_raw, kankersoort_raw)

        # Normalize section to one of the 6 canonical sections
        if section_raw in CANONICAL_SECTIONS:
            section = section_raw
        elif section_raw in SECTION_ALIAS_MAP:
            section = SECTION_ALIAS_MAP[section_raw]
        else:
            section = section_raw if section_raw else "algemeen"

        title = extract_title(text)

        candidates[norm_url] = {
            "kankersoort": kankersoort,
            "section": section,
            "url": norm_url,
            "title": title,
            "text": text,
            "text_length": len(text),
        }

    print(f"  Skipped {skipped_errors} error/broken pages")
    print(f"  Merged {skipped_dupes} duplicate URLs")

    # --- Pass 2: Deduplicate content across kankersoort aliases ---
    # For botkanker/botkanker-botsarcoom and wekedelentumoren/wekedelentumoren-wekedelensarcomen,
    # pages may exist under both slugs with identical content.  Keep only the
    # canonical (longer) slug version.
    final: dict[str, dict] = {}
    deduped_alias = 0

    for norm_url, entry in candidates.items():
        # Check if there's an equivalent under the canonical slug
        skip = False
        for old_slug, new_slug in KANKERSOORT_CANONICAL_MAP.items():
            old_prefix = f"{CANONICAL_PREFIX}kankersoorten/{old_slug}/"
            new_prefix = f"{CANONICAL_PREFIX}kankersoorten/{new_slug}/"
            if norm_url.startswith(old_prefix):
                canonical_url = norm_url.replace(old_prefix, new_prefix, 1)
                if canonical_url in candidates:
                    # Canonical version exists — skip the old-slug version
                    deduped_alias += 1
                    skip = True
                    break
                else:
                    # Old slug only — rewrite the URL to the canonical slug
                    entry = {**entry, "url": canonical_url, "kankersoort": new_slug}
                    norm_url = canonical_url
                    break
        if not skip:
            final[norm_url] = entry

    print(f"  Deduped {deduped_alias} alias pages (botkanker/wekedelentumoren)")

    # Strip the raw text from the sitemap output (it's only needed for dedup)
    # but keep text_length as metadata
    sitemap_entries = []
    for entry in final.values():
        sitemap_entries.append({
            "kankersoort": entry["kankersoort"],
            "section": entry["section"],
            "url": entry["url"],
            "title": entry["title"],
            "text_length": entry["text_length"],
        })

    # Sort for deterministic output
    sitemap_entries.sort(key=lambda e: (e["kankersoort"], e["section"], e["url"]))

    print(f"  Final sitemap: {len(sitemap_entries)} pages")
    print(f"  Unique kankersoorten: {len(set(e['kankersoort'] for e in sitemap_entries))}")
    return sitemap_entries


def main():
    sitemap = build_sitemap()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(sitemap, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {OUTPUT_PATH} ({len(sitemap)} entries)")


if __name__ == "__main__":
    main()
