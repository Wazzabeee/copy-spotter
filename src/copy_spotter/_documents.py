"""Documents to compare: reading them from text, bytes or files, and finding them in a directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from copy_spotter._errors import DocumentReadError
from copy_spotter.extract import clean_text, format_of, is_supported, read_text, tokenize_with_offsets


@dataclass(frozen=True)
class Document:
    """A document ready to compare: its display text, its words and where each word is in the text.

    ``words[k]`` is the k-th word in lowercase and ``text[spans[k][0]:spans[k][1]]`` the same word as written.
    Words are runs of letters and digits; matching works on words only, so case, punctuation and line breaks
    never change the results.

    Attributes:
        name: Identifies the document in reports and exports; unique within a comparison.
        text: The text shown in reports, with tidied line breaks.
        words: The lowercase words of ``text``, in order.
        spans: The ``(start, end)`` character range of each word in ``text``.
    """

    name: str
    text: str
    words: tuple[str, ...]
    spans: tuple[tuple[int, int], ...]

    @classmethod
    def from_text(cls, text: str, name: str, *, join_lines: bool = False) -> Document:
        """Build a document from plain text.

        Args:
            text: The text of the document.
            name: The name of the document in reports.
            join_lines: Join the lines of a paragraph that were hard-wrapped (what PDF text needs).
        """
        cleaned = clean_text(text, join_lines=join_lines)
        words, spans = tokenize_with_offsets(cleaned)
        return cls(name, cleaned, tuple(words), tuple(spans))

    @classmethod
    def from_bytes(cls, data: bytes, name: str, *, format: str | None = None) -> Document:
        """Read a pdf, docx, odt or txt file held in memory.

        Args:
            data: The content of the file.
            name: The name of the document in reports, usually its file name.
            format: ``"pdf"``, ``"docx"``, ``"odt"`` or ``"txt"`` (case-insensitive, with or without a leading
                dot). Defaults to the extension of ``name``.

        Raises:
            UnsupportedFormatError: The format is not supported.
            DocumentReadError: The file could not be parsed; the parser's error is its ``__cause__``.
        """
        fmt = format_of(name, format)
        try:
            raw = read_text(data, fmt)
        except Exception as exc:
            raise DocumentReadError(f"Could not read {name}: {exc}") from exc
        return cls.from_text(raw, name, join_lines=fmt == "pdf")

    @classmethod
    def from_path(cls, path: str | Path, *, name: str | None = None) -> Document:
        """Read a pdf, docx, odt or txt file from disk; the format is given by its extension.

        Args:
            path: The file to read.
            name: The name of the document in reports. Defaults to the file name.

        Raises:
            FileNotFoundError: ``path`` is not a file.
            UnsupportedFormatError: The extension is not supported.
            DocumentReadError: The file could not be parsed; the parser's error is its ``__cause__``.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Not a file: {path}")
        fmt = format_of(path.name)
        return cls.from_bytes(path.read_bytes(), path.name if name is None else name, format=fmt)


def find_documents(directory: str | Path, *, recursive: bool = False, exclude: str | Path | None = None) -> list[Path]:
    """Return the supported, non-hidden files of ``directory``, sorted by path.

    Files under ``exclude`` (for instance the output directory) are left out.
    """
    directory = Path(directory)
    excluded = None if exclude is None else Path(exclude).resolve()
    candidates = directory.rglob("*") if recursive else directory.iterdir()
    documents = []
    for path in candidates:
        if not path.is_file() or not is_supported(path) or path.name.startswith("."):
            continue
        if excluded is not None and path.resolve().is_relative_to(excluded):
            continue
        documents.append(path)
    return sorted(documents)
