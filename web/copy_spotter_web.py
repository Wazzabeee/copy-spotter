"""Glue between the web app's worker and copy-spotter: compare files held in memory.

The worker writes this file into Pyodide's in-memory filesystem and calls :func:`analyze`. It only uses the public
API of copy-spotter and mirrors what the command line does: unreadable or empty files are skipped with a reason,
documents are sorted by name, and the report, JSON and CSV are those of ``copy-spotter --json --csv``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import PurePosixPath
from typing import Any

from copy_spotter import (
    CopySpotterError,
    Document,
    Progress,
    __version__,
    compare_documents,
)

# progress(stage, done, total): stage is "read" or "compare".
ProgressFn = Callable[[str, int, int], None]


def _as_bytes(data: Any) -> bytes:
    """Return the bytes of ``data``: bytes in CPython, a Uint8Array proxy in Pyodide."""
    to_bytes = getattr(data, "to_bytes", None)
    return bytes(to_bytes()) if to_bytes is not None else bytes(data)


def _throttled(progress: ProgressFn | None) -> Callable[[Progress], None]:
    """Forward compare events, at most one per percent, plus the first and the last."""
    last = -1

    def forward(event: Progress) -> None:
        nonlocal last
        step = event.done * 100 // max(event.total, 1)
        if progress is not None and (step != last or event.done in (0, event.total)):
            last = step
            progress(event.stage, event.done, event.total)

    return forward


def _error_text(exc: Exception) -> str:
    cause = exc.__cause__ or exc
    return str(cause) or type(cause).__name__


def analyze(
    files: Iterable[Sequence[Any]],
    *,
    block_size: int = 2,
    engine: str = "shingle",
    score: str = "coverage",
    thresholds: Iterable[float] = (5, 10, 15),
    progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Read and compare in-memory files.

    Args:
        files: ``(name, data)`` pairs. ``name`` is the path relative to the chosen folder, unique, and its extension
            gives the format; ``data`` is the file's content.
        block_size: See :func:`copy_spotter.compare_documents`.
        engine: See :func:`copy_spotter.compare_documents`.
        score: See :meth:`copy_spotter.Results.to_html`.
        thresholds: See :meth:`copy_spotter.Results.to_html`.
        progress: Called as ``progress(stage, done, total)`` while files are read and pairs compared.

    Returns:
        On success ``{"html", "json", "csv", "names", "skipped", "version"}``. ``skipped`` lists
        ``{"name", "reason", "detail"}`` for files left out. When fewer than two documents are readable, or an option
        is invalid, ``{"error", "skipped"}`` instead.
    """
    entries = sorted(((str(name), data) for name, data in files), key=lambda entry: PurePosixPath(entry[0]).parts)
    documents: list[Document] = []
    skipped: list[dict[str, str]] = []
    if progress is not None:
        progress("read", 0, len(entries))
    for done, (name, data) in enumerate(entries, 1):
        try:
            document = Document.from_bytes(_as_bytes(data), name)
        except CopySpotterError as exc:
            skipped.append({"name": name, "reason": "unreadable", "detail": _error_text(exc)})
        else:
            if document.words:
                documents.append(document)
            else:
                skipped.append({"name": name, "reason": "empty", "detail": ""})
        if progress is not None:
            progress("read", done, len(entries))
    if len(documents) < 2:
        return {"error": f"Need at least two readable documents, found {len(documents)}.", "skipped": skipped}
    try:
        results = compare_documents(
            documents,
            block_size=block_size,
            engine=engine,
            progress=_throttled(progress),
        )
        thresholds = tuple(thresholds)
        return {
            "html": results.to_html(score=score, thresholds=thresholds),
            "json": results.to_json(score=score, thresholds=thresholds),
            "csv": results.to_csv(score=score),
            "names": [document.name for document in documents],
            "skipped": skipped,
            "version": __version__,
        }
    except ValueError as exc:
        return {"error": str(exc), "skipped": skipped}
