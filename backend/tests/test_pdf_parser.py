import pytest

from app.utils.pdf_parser import extract_text_from_pdf, CorruptPDFError


def test_extract_text_from_pdf_rejects_corrupt_file(tmp_path):
    bad_path = tmp_path / "not_really_a_pdf.pdf"
    bad_path.write_bytes(b"this is definitely not a valid PDF file")

    with pytest.raises(CorruptPDFError):
        extract_text_from_pdf(str(bad_path))


def test_extract_text_from_pdf_error_message_is_user_friendly(tmp_path):
    bad_path = tmp_path / "broken.pdf"
    bad_path.write_bytes(b"%PDF-1.4\ngarbage garbage garbage")

    with pytest.raises(ValueError, match="could not be read|corrupted"):
        extract_text_from_pdf(str(bad_path))
        