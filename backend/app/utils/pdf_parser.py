"""
pdf_parser.py
─────────────
Thin wrapper around pdfplumber that turns the various ways a PDF can be
unreadable (corrupt, password-protected, zero pages) into clear
ValueErrors the routers can turn into a 400 for the user, instead of a
raw traceback bubbling up as a 500.
"""

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
    