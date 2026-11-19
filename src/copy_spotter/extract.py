"""Text extraction from pdf, docx, odt, txt, md, html, rtf and ipynb files.

Readers take the file content as bytes, so documents can come from memory as well as from disk. The parsers
(pdfminer, odfpy) are imported on first use: importing copy-spotter stays fast and only the formats in use load.
The markup readers (Markdown, HTML, RTF, notebooks) only use the standard library.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree

from copy_spotter._errors import UnsupportedFormatError
from copy_spotter._formats import TXT_ENCODINGS, read_html, read_ipynb, read_markdown, read_rtf

SUPPORTED_FORMATS = ("pdf", "docx", "odt", "txt", "md", "html", "htm", "rtf", "ipynb")
SUPPORTED_EXTENSIONS = tuple(f".{fmt}" for fmt in SUPPORTED_FORMATS)

_WORD_RE = re.compile(r"\w+")
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# Display cleanup. Each rule replaces a run of whitespace with non-empty whitespace (or trims the
# ends), so the words found in the text never change.
_TRAILING_SPACE_RE = re.compile(r"[^\S\n]+\n")
_PARAGRAPH_BREAK_RE = re.compile(r"\n{2,}")
# A single line break inside a paragraph, unless the next line starts a list item (bullet or "1." / "1)").
_LIST_MARKER = r"(?:[-*\u2022\u25aa\u25e6\u2023\u2043]|\d+[.)])\s"
_SOFT_LINE_BREAK_RE = re.compile(rf"(?<=[^\n])\n[^\S\n]*(?=\S)(?!{_LIST_MARKER})")


def is_supported(path: Path) -> bool:
    """Return True if the file extension is supported (case-insensitive)."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def tokenize(content: str) -> list[str]:
    """Split text into lowercase words."""
    return _WORD_RE.findall(content.lower())


def tokenize_with_offsets(content: str) -> tuple[list[str], list[tuple[int, int]]]:
    """Split text into the same words as :func:`tokenize` and the ``(start, end)`` span of each word in ``content``."""
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
    return words, spans


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


def format_of(name: str, format: str | None = None) -> str:
    """Return the format (``"pdf"``, ...) given by ``format`` or else by the extension of ``name``.

    Raises:
        UnsupportedFormatError: the format is not one of :data:`SUPPORTED_FORMATS`.
    """
    fmt = (Path(name).suffix if format is None else format).lower().removeprefix(".")
    if fmt not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(
            f"Unsupported file format: {name}. Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return fmt


def read_pdf(data: bytes) -> str:
    """Return the text of a PDF file. Scanned PDFs without a text layer return an empty string."""
    from pdfminer.high_level import extract_text  # noqa: PLC0415 - slow import, only needed for PDFs

    return str(extract_text(io.BytesIO(data)))


def read_txt(data: bytes) -> str:
    """Return the content of a text file, trying common encodings."""
    for encoding in TXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AssertionError("unreachable: latin-1 decodes any byte sequence")  # pragma: no cover


def read_docx(data: bytes) -> str:
    """Return the text of a DOCX file, one line per paragraph."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
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


def read_odt(data: bytes) -> str:
    """Return the text of an ODT file (headings and paragraphs), one line per block."""
    from odf import teletype  # noqa: PLC0415 - only needed for ODT files
    from odf.namespaces import TEXTNS  # noqa: PLC0415
    from odf.opendocument import load  # noqa: PLC0415

    text_blocks = ((TEXTNS, "p"), (TEXTNS, "h"))

    def blocks_of(node: object) -> list[str]:
        if getattr(node, "qname", None) in text_blocks:
            return [str(teletype.extractText(node))]
        blocks: list[str] = []
        for child in getattr(node, "childNodes", []):
            blocks.extend(blocks_of(child))
        return blocks

    document = load(io.BytesIO(data))
    blocks = []
    # Walk the body in document order so headings stay where they belong.
    for node in document.text.childNodes:
        blocks.extend(blocks_of(node))
    return "\n".join(blocks)


_READERS: dict[str, Callable[[bytes], str]] = {
    "pdf": read_pdf,
    "docx": read_docx,
    "odt": read_odt,
    "txt": read_txt,
    "md": read_markdown,
    "html": read_html,
    "htm": read_html,
    "rtf": read_rtf,
    "ipynb": read_ipynb,
}


def read_text(data: bytes, format: str) -> str:
    """Return the raw text of a file of a supported ``format`` (as returned by :func:`format_of`)."""
    return _READERS[format](data)


def extract_text(path: str | Path) -> str:
    """Return the raw text of a supported document on disk."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    fmt = format_of(path.name)
    return read_text(path.read_bytes(), fmt)


def extract_words(path: str | Path) -> list[str]:
    """Return the lowercase words of a supported document on disk."""
    path = Path(path)
    return tokenize(clean_text(extract_text(path), join_lines=format_of(path.name) == "pdf"))
