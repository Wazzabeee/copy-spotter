from __future__ import annotations

import dataclasses
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path

import pytest

from copy_spotter._compare import Pair
from copy_spotter._documents import Document
from copy_spotter._results import Results
from copy_spotter.extract import tokenize_with_offsets
from copy_spotter.similarity import Engine, Match

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PLAGIARISM_DIR = DATA_DIR / "pdf" / "plagiarism"

_DOCX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    "</Types>"
)


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    """Write a minimal DOCX file with one paragraph per string."""
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        archive.writestr("word/document.xml", document)
    return path


def make_document(text: str, name: str = "doc.txt") -> Document:
    """Return a document whose display text is exactly ``text`` (no cleanup)."""
    words, spans = tokenize_with_offsets(text)
    return Document(name, text, tuple(words), tuple(spans))


def make_pair(  # noqa: PLR0917 - mirrors the field order of Pair to keep the test tables short
    i: int, j: int, ratio: float, blocks: Iterable[Match], coverage_i: float, coverage_j: float
) -> Pair:
    return Pair(i=i, j=j, ratio=ratio, coverage_i=coverage_i, coverage_j=coverage_j, blocks=tuple(blocks))


def make_results(
    names: Sequence[str],
    pairs: Iterable[Pair],
    documents: Sequence[Document] | None = None,
    *,
    block_size: int = 2,
    engine: Engine = "shingle",
) -> Results:
    """Results over ``documents`` renamed to ``names`` (by default, one-word documents)."""
    if documents is None:
        documents = [make_document("x") for _ in names]
    renamed = tuple(dataclasses.replace(d, name=n) for n, d in zip(names, documents, strict=True))
    return Results(documents=renamed, pairs=tuple(pairs), block_size=block_size, engine=engine)


@pytest.fixture
def plagiarism_dir() -> Path:
    return PLAGIARISM_DIR
