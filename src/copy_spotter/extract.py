"""Text extraction from pdf, docx, odt and txt files."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
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


# Display cleanup. Each rule replaces a run of whitespace with non-empty whitespace (or trims the
# ends), so the words found in the text never change.
_TRAILING_SPACE_RE = re.compile(r"[^\S\n]+\n")
_PARAGRAPH_BREAK_RE = re.compile(r"\n{2,}")
# A single line break inside a paragraph, unless the next line starts a list item (bullet or "1." / "1)").
_LIST_MARKER = r"(?:[-*\u2022\u25aa\u25e6\u2023\u2043]|\d+[.)])\s"
_SOFT_LINE_BREAK_RE = re.compile(rf"(?<=[^\n])\n[^\S\n]*(?=\S)(?!{_LIST_MARKER})")


class UnsupportedFileError(ValueError):
    """Raised when a file extension is not supported."""


@dataclass(frozen=True)
class Document:
    """A document's display text, its lowercase words and the ``(start, end)`` character span of each word."""

    text: str
    words: list[str]
    spans: list[tuple[int, int]]


def is_supported(path: Path) -> bool:
    """Return True if the file extension is supported (case-insensitive)."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def tokenize(content: str) -> list[str]:
    """Split text into lowercase words."""
    return _WORD_RE.findall(content.lower())


def tokenize_with_offsets(content: str) -> Document:
    """Split text into the same words as :func:`tokenize`, keeping each word's span in ``content``."""
    lowered = content.lower()
    # Lowercasing can lengthen a character ("\u0130" becomes "i" plus a combining dot): map positions back.
    index: list[int] | None = None
    if len(lowered) != len(content):
        index = [i for i, char in enumerate(content) for _ in char.lower()]
    words, spans = [], []
    for match in _WORD_RE.finditer(lowered):
        start, end = match.span()
        if index is not None:
            start, end = index[start], index[end - 1] + 1
        words.append(match.group())
        spans.append((start, end))
    return Document(content, words, spans)


def clean_text(content: str, join_lines: bool = False) -> str:
    """Tidy text for display: normalize line breaks and paragraph breaks, trim trailing spaces.

    With ``join_lines`` (PDF), single line breaks inside a paragraph become spaces. The words of the text are
    never changed.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    content = _TRAILING_SPACE_RE.sub("\n", content)
    content = _PARAGRAPH_BREAK_RE.sub("\n\n", content)
    if join_lines:
        content = _SOFT_LINE_BREAK_RE.sub(" ", content)
    return content.strip()


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


def extract_document(path: str | Path) -> Document:
    """Return the cleaned text of a supported document with its words and their positions."""
    path = Path(path)
    text = clean_text(extract_text(path), join_lines=path.suffix.lower() == ".pdf")
    return tokenize_with_offsets(text)


def extract_words(path: str | Path) -> list[str]:
    """Return the lowercase words of a supported document."""
    return extract_document(path).words
