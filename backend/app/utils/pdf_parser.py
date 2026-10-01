"""
pdf_parser.py
─────────────
Thin wrapper around pdfplumber that turns the various ways a PDF can be
unreadable (corrupt, password-protected, zero pages) into clear
ValueErrors the routers can turn into a 400 for the user, instead of a
raw traceback bubbling up as a 500.

extract_text_from_pdf()     — flat text, unchanged, still used for the
                               raw_text column and for grounding checks.
extract_sections_from_pdf() — NEW: (heading, body_text) pairs, using
                               font size / boldness as the heading signal
                               (pdfplumber already exposes per-char font
                               metadata, so this needs no new dependency).
extract_toc_headings()      — NEW: pulls a literal "1. Title .... 12"
                               index/TOC page if the document has one;
                               used to sanity-check / override the
                               font-size heading guesses.
"""

import re
from statistics import median

import pdfplumber


class PasswordProtectedPDFError(ValueError):
    pass


class CorruptPDFError(ValueError):
    pass


def extract_text_from_pdf(file_path: str) -> str:
    try:
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) == 0:
                raise CorruptPDFError("This PDF has no pages.")

            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            return text

    except CorruptPDFError:
        raise
    except Exception as e:
        message = str(e).lower()
        if "password" in message or "encrypt" in message:
            raise PasswordProtectedPDFError(
                "This PDF is password-protected. Please upload an unlocked copy."
            ) from e
        raise CorruptPDFError(
            "This PDF could not be read — it may be corrupted or in an unsupported format."
        ) from e


# Matches a TOC/index row like "3.  Anti-ragging Policy ........ 16"
# or "3   Anti-ragging Policy   16" (dot-leader is optional).
_TOC_ROW = re.compile(r"^\s*\d{1,3}[.)]?\s+(.+?)\s*(?:\.{2,}|\s{2,})\s*\d{1,4}\s*$")

# Headings should be short — a body sentence that happens to be bold
# shouldn't be treated as one.
_MAX_HEADING_LEN = 90


def extract_toc_headings(file_path: str, max_pages: int = 4) -> list[str]:
    """
    Looks at the first few pages for a literal table of contents / index
    and returns the section titles in order, e.g. ["Code of Conduct",
    "Divyangjan Policy", "Anti-ragging Policy", ...].

    Returns [] if no TOC-shaped page is found — callers should fall back
    to extract_sections_from_pdf()'s font-size heuristic in that case.
    """
    headings: list[str] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:max_pages]:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    m = _TOC_ROW.match(line)
                    if m:
                        headings.append(m.group(1).strip())
    except Exception:
        return []
    return headings


def extract_sections_from_pdf(file_path: str) -> list[dict]:
    """
    Splits the document into [{"heading": str, "text": str}, ...] using
    font size / bold weight as the heading signal, instead of blind
    character-count chunking. This is what lets schema generation and
    extraction be scoped per section instead of per arbitrary 5000-char
    window.

    Falls back to a single {"heading": "Document", "text": <all text>}
    section if no heading-like lines are detected (e.g. a plain-text PDF
    with no font variation) — callers should treat that as "no structure
    detected" rather than fail.
    """
    with pdfplumber.open(file_path) as pdf:
        if len(pdf.pages) == 0:
            raise CorruptPDFError("This PDF has no pages.")

        all_chars = [c for page in pdf.pages for c in page.chars]
        if not all_chars:
            raise CorruptPDFError("This PDF could not be read — it may be scanned/imageonly.")

        body_size = median(c["size"] for c in all_chars)
        heading_size_threshold = body_size * 1.15  # tune per corpus if needed

        sections: list[dict] = []
        current = {"heading": "Document Start", "text": ""}

        for page in pdf.pages:
            try:
                lines = page.extract_text_lines()
            except AttributeError:
                # Older pdfplumber without extract_text_lines(): degrade
                # to flat text for this page, no heading detection on it.
                current["text"] += (page.extract_text() or "") + "\n"
                continue

            for line in lines:
                line_text = (line.get("text") or "").strip()
                if not line_text:
                    continue

                line_chars = line.get("chars") or []
                if not line_chars:
                    current["text"] += line_text + "\n"
                    continue

                avg_size = sum(c["size"] for c in line_chars) / len(line_chars)
                is_bold = any("bold" in (c.get("fontname") or "").lower() for c in line_chars)
                looks_like_heading = (
                    (avg_size >= heading_size_threshold or is_bold)
                    and len(line_text) <= _MAX_HEADING_LEN
                    and not line_text.endswith((".", ",", ";"))  # body sentences end in punctuation
                )

                if looks_like_heading:
                    if current["text"].strip():
                        sections.append(current)
                    current = {"heading": line_text, "text": ""}
                else:
                    current["text"] += line_text + "\n"

        if current["text"].strip():
            sections.append(current)

        if not sections:
            return [{"heading": "Document", "text": extract_text_from_pdf(file_path)}]

        return sections
    