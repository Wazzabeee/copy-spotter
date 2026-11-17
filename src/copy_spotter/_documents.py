"""Documents to compare: reading them from text, bytes or files, and finding them in a directory."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from copy_spotter._errors import CopySpotterError, DocumentReadError
from copy_spotter._progress import ProgressCallback, emit
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


@dataclass(frozen=True)
class Skipped:
    """A file that :func:`load_directory` left out.

    Attributes:
        name: The file's path relative to the directory, with ``/`` separators.
        reason: ``"unreadable"`` (see ``error``) or ``"empty"`` (no words, for instance a scanned PDF).
        error: Why the file could not be read: a :class:`DocumentReadError` whose ``__cause__`` is the parser
            error, or an ``OSError``. ``None`` for empty files.
    """

    name: str
    reason: Literal["unreadable", "empty"]
    error: Exception | None = None


def load_directory(
    directory: str | Path,
    *,
    recursive: bool = False,
    exclude: str | Path | None = None,
    on_skip: Callable[[Skipped], None] | None = None,
    progress: ProgressCallback | None = None,
) -> list[Document]:
    """Read every supported document of a directory.

    Hidden files and files in other formats are ignored. Files that cannot be read and files without any word
    are left out and reported to ``on_skip``, so one corrupt file does not stop the run.

    Args:
        directory: The directory to read.
        recursive: Also read the documents of subdirectories.
        exclude: Leave out the files under this path (for instance an output directory inside ``directory``).
        on_skip: Called with a :class:`Skipped` for each file left out.
        progress: Called with a :class:`Progress` event (stage ``"read"``) before the first file and after each
            file.

    Returns:
        The documents, sorted by path. Each is named by its path relative to ``directory``, with ``/``.

    Raises:
        NotADirectoryError: ``directory`` is not a directory.
    """
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")
    paths = find_documents(root, recursive=recursive, exclude=exclude)
    documents = []
    emit(progress, "read", 0, len(paths))
    for done, path in enumerate(paths, 1):
        name = path.relative_to(root).as_posix()
        try:
            document = Document.from_path(path, name=name)
        except (OSError, CopySpotterError) as exc:
            if on_skip is not None:
                on_skip(Skipped(name, "unreadable", exc))
        else:
            if document.words:
                documents.append(document)
            elif on_skip is not None:
                on_skip(Skipped(name, "empty"))
        emit(progress, "read", done, len(paths))
    return documents
