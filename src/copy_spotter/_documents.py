"""Finding the documents to compare."""

from __future__ import annotations

from pathlib import Path

from copy_spotter.extract import is_supported


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
