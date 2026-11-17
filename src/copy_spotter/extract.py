"""Text extraction from pdf, docx, odt and txt files."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree

from odf import teletype
from odf.namespaces import TEXTNS
from odf.opendocument import load as load_odt
from pdfminer.high_level import extract_text as extract_pdf_text

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".odt", ".txt")

# Encodings tried in order for plain text files. cp1252 is a superset of latin-1 for printable
# characters and is what most Windows editors produce; latin-1 never fails and acts as last resort.
_TXT_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")

_WORD_RE = re.compile(r"\w+")
_ODT_TEXT_BLOCKS = ((TEXTNS, "p"), (TEXTNS, "h"))
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class UnsupportedFileError(ValueError):
    """Raised when a file extension is not supported."""


def is_supported(path: Path) -> bool:
    """Return True if the file extension is supported (case-insensitive)."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def tokenize(content: str) -> list[str]:
    """Split text into lowercase words."""
    return _WORD_RE.findall(content.lower())


def read_pdf(path: Path) -> str:
    """Return the text of a PDF file. Scanned PDFs without a text layer return an empty string."""
    return str(extract_pdf_text(str(path)))


def read_txt(path: Path) -> str:
    """Return the content of a text file, trying common encodings."""
    raw = path.read_bytes()
    for encoding in _TXT_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AssertionError("unreachable: latin-1 decodes any byte sequence")  # pragma: no cover


def read_docx(path: Path) -> str:
    """Return the text of a DOCX file, one line per paragraph."""
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))

    paragraphs = []
    for paragraph in root.iter(f"{_W_NS}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{_W_NS}t" and node.text:
                parts.append(node.text)
            elif node.tag in (f"{_W_NS}tab", f"{_W_NS}br", f"{_W_NS}cr"):
                parts.append(" ")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def read_odt(path: Path) -> str:
    """Return the text of an ODT file (headings and paragraphs), one line per block."""
    document = load_odt(str(path))
    blocks = []
    # Walk the body in document order so headings stay where they belong.
    for node in document.text.childNodes:
        blocks.extend(_odt_blocks(node))
    return "\n".join(blocks)


def _odt_blocks(node: object) -> list[str]:
    qname = getattr(node, "qname", None)
    if qname in _ODT_TEXT_BLOCKS:
        return [str(teletype.extractText(node))]
    blocks: list[str] = []
    for child in getattr(node, "childNodes", []):
        blocks.extend(_odt_blocks(child))
    return blocks


_READERS: dict[str, Callable[[Path], str]] = {
    ".pdf": read_pdf,
    ".docx": read_docx,
    ".odt": read_odt,
    ".txt": read_txt,
}


def extract_text(path: str | Path) -> str:
    """Return the raw text of a supported document."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        raise UnsupportedFileError(
            f"Unsupported file format: {path.name}. Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return reader(path)


def extract_words(path: str | Path) -> list[str]:
    """Return the lowercase words of a supported document."""
    return tokenize(extract_text(path))
