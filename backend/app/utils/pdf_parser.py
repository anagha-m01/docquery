"""
pdf_parser.py
─────────────
Thin wrapper around pdfplumber that turns the various ways a PDF can be
unreadable (corrupt, password-protected, zero pages) into clear
ValueErrors the routers can turn into a 400 for the user, instead of a
raw traceback bubbling up as a 500.

extract_text_from_pdf()     — flat text, unchanged, still used for the
                               raw_text column and for grounding checks.
extract_sections_from_pdf() — (heading, body_text, tables) triples, using
                               font size/bold as the heading signal, with
                               table regions EXCLUDED from that heading
                               walk (v2 fix — see note below) and each
                               table attached to its owning section as
                               structured rows instead of prose text.
extract_toc_headings()      — pulls a literal "1. Title .... 12"
                               index/TOC page if the document has one.

--- v2 fix note ---
Tested extract_sections_from_pdf() against a real multi-page policy PDF
with no TOC page. It correctly caught numbered sub-headings like "1.1
Scope", "1.3 Security training" — but ALSO misread every table's header
row ("Role | Primary responsibilities", "Event | Required action |
Target time", etc.) as a section heading, because those header rows are
bold at the same size as real headings. That's what was producing schema
keys like "role_primary_responsibilities" and
"event_required_action_target_time" instead of the actual heading
("1.2 Roles", "3.3 Joiner, mover and leaver controls").

Fix: use page.find_tables() to get each table's bounding box up front,
and skip any line whose vertical position falls inside a table's bbox
during the heading/paragraph walk — then extract that table separately
with page.extract_tables() and attach it to whichever heading currently
owns that part of the page, as structured rows instead of flattened
prose. A table's cells also get scanned for glyph-level corruption (see
below) and flagged rather than silently trusted.

--- separate, NOT fixable in code ---
Two of the tables in that same test PDF contain text where individual
LETTERS from two adjacent table cells are interleaved at the glyph
level, e.g. "selecteRde ssterricvtieced data" instead of "selected
service" / "Restricted data ...". This was verified directly against
page.chars sorted purely by x-position — the glyphs are genuinely placed
in that order in the PDF's content stream, not a pdfplumber
line-clustering artifact. No text-extraction tuning recovers this; the
defect is in the source PDF itself (almost certainly a text-wrapping bug
in whatever tool generated it, where a wrapped continuation line in one
column landed at the same height as another column's line). The
practical response is not to try to parse around it, but to flag it —
contains_glyph_corruption() below does a cheap heuristic check so a
downstream caller can mark the field for human review instead of
silently trusting garbled text as ground truth.
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

_MAX_HEADING_LEN = 90

# A word with a lowercase-to-uppercase-to-lowercase transition in its
# middle is not a normal English/camelCase token in prose — it's the
# signature this doc's corrupted tables leave behind ("selecteRde",
# "documentSathioanre").
_GLYPH_CORRUPTION = re.compile(r"\b[a-z]{2,}[A-Z][a-z]{2,}[A-Za-z]*\b")


def contains_glyph_corruption(text: str) -> bool:
    """Cheap heuristic flag for the interleaved-glyph defect described
    above. False positives are possible (a real camelCase identifier
    quoted in the doc) but rare in prose/table text, so this is meant as
    a "flag for human review" signal, not an auto-corrector."""
    return bool(_GLYPH_CORRUPTION.search(text or ""))


def extract_toc_headings(file_path: str, max_pages: int = 4) -> list[str]:
    """
    Looks at the first few pages for a literal table of contents / index
    and returns the section titles in order. Returns [] if no TOC-shaped
    page is found — callers should rely on extract_sections_from_pdf()'s
    font-size heuristic in that case.
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


def _table_bboxes(page) -> list[tuple[float, float, float, float]]:
    """(x0, top, x1, bottom) for every table pdfplumber finds on this page."""
    try:
        return [t.bbox for t in page.find_tables()]
    except Exception:
        return []


def _line_in_any_bbox(line_top: float, line_bottom: float, bboxes) -> bool:
    # Strict containment (1pt slack). A loose overlap test swallowed
    # headings like "1.2 Roles" that sit directly above their table.
    for (_, t, _, b) in bboxes:
        if line_top >= t - 1 and line_bottom <= b + 1:
            return True
    return False


def extract_sections_from_pdf(file_path: str) -> list[dict]:
    """
    Splits the document into
        [{"heading": str, "text": str, "tables": [{"columns": [...], "rows": [...]}]}]
    using font size/bold as the heading signal, with table regions
    excluded from that walk (see module docstring) and extracted
    separately as structured rows attached to the section they fall
    under.

    Falls back to a single {"heading": "Document", "text": <all text>,
    "tables": []} section if no heading-like lines are detected.
    """
    with pdfplumber.open(file_path) as pdf:
        if len(pdf.pages) == 0:
            raise CorruptPDFError("This PDF has no pages.")

        all_chars = [c for page in pdf.pages for c in page.chars]
        if not all_chars:
            raise CorruptPDFError("This PDF could not be read — it may be scanned/imageonly.")

        body_size = median(c["size"] for c in all_chars)
        heading_size_threshold = body_size * 1.15

        sections: list[dict] = []
        current = {"heading": "Document Start", "text": "", "tables": []}

        for page in pdf.pages:
            found_tables = page.find_tables()
            table_bboxes = [t.bbox for t in found_tables]

            try:
                lines = page.extract_text_lines()
            except AttributeError:
                current["text"] += (page.extract_text() or "") + "\n"
                continue

            # Walk lines AND tables in vertical order so each table is
            # attached to the heading that is active where the table
            # actually sits on the page, not where the page started.
            events = [("line", ln.get("top", 0), ln) for ln in lines]
            events += [("table", t.bbox[1], t) for t in found_tables]
            events.sort(key=lambda e: e[1])

            for kind, _, obj in events:
                if kind == "table":
                    raw_table = obj.extract()
                    if not raw_table or len(raw_table) < 2:
                        continue
                    header = [(h or "").strip() for h in raw_table[0]]
                    rows = []
                    for row in raw_table[1:]:
                        row_dict = {
                            header[i] if i < len(header) else f"col_{i}": (cell or "").strip()
                            for i, cell in enumerate(row)
                        }
                        for cell_val in row_dict.values():
                            if contains_glyph_corruption(cell_val):
                                row_dict["_extraction_warning"] = (
                                    "possible source-PDF text corruption — verify against original"
                                )
                                break
                        rows.append(row_dict)
                    current["tables"].append({"columns": header, "rows": rows})
                    continue

                line = obj
                line_top = line.get("top", 0)
                line_bottom = line.get("bottom", line_top)
                if _line_in_any_bbox(line_top, line_bottom, table_bboxes):
                    continue  # captured structurally as a table

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
                    and not line_text.endswith((".", ",", ";"))
                )

                if looks_like_heading:
                    if current["text"].strip() or current["tables"]:
                        sections.append(current)
                    current = {"heading": line_text, "text": "", "tables": []}
                else:
                    current["text"] += line_text + "\n"

        if current["text"].strip() or current["tables"]:
            sections.append(current)

        if not sections:
            return [{"heading": "Document", "text": extract_text_from_pdf(file_path), "tables": []}]

        return sections
    