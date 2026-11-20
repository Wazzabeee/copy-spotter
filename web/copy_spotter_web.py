"""Glue between the web app's worker and copy-spotter: compare files held in memory.

The worker writes this file into Pyodide's in-memory filesystem and calls :func:`analyze`. It only uses the public
API of copy-spotter and mirrors what the command line does: unreadable or empty files are skipped with a reason,
documents are sorted by name, and the report, JSON and CSV are those of ``copy-spotter --json --csv``.

A browser tab has a single thread and a few GB of memory at most (a wasm32 heap cannot grow past 4 GB), so the web
app is stricter than the command line: blocks of at least :data:`MIN_BLOCK_SIZE` words, and limits on the number of
documents and words (:data:`LIMITS`). Measured in Pyodide on generated English-like documents of 1000 to 3000 words
with a block size of 4: 200 documents (412k words) took 5 s and 270 MB, 500 documents (1M words) 48 s and 670 MB,
1000 documents (2M words) 131 s and 1.2 GB. With a block size of 2, 500 documents needed a 3.5 GB heap.
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
# notice(text): a warning to show while the comparison runs.
NoticeFn = Callable[[str], None]

MIN_BLOCK_SIZE = 4
LIMITS = {
    "warn_documents": 200,
    "warn_words": 400_000,
    "max_documents": 1000,
    "max_words": 2_000_000,
}
# Cost model fitted on the measurements above (block size 4): heap and time grow with the words and the pairs.
_BASE_MB, _MB_PER_1000_WORDS, _SECONDS_PER_1000_PAIRS = 30, 0.6, 0.3


def estimate(documents: int, words: int) -> dict[str, int]:
    """Return the expected number of pairs, memory (MB) and compare time (seconds) of a run in the browser."""
    pairs = documents * (documents - 1) // 2
    return {
        "pairs": pairs,
        "memory_mb": round(_BASE_MB + _MB_PER_1000_WORDS * words / 1000),
        "seconds": round(_SECONDS_PER_1000_PAIRS * pairs / 1000),
    }


def check_size(documents: int, words: int) -> tuple[str, str]:
    """Return ``(level, message)``: level ``"ok"``, ``"warn"`` (large, slow but allowed) or ``"refuse"`` (too large)."""
    cost = estimate(documents, words)
    size = f"{documents} documents" + (f", {words:,} words, {cost['pairs']:,} pairs" if words else "")
    if documents > LIMITS["max_documents"] or words > LIMITS["max_words"]:
        return "refuse", (
            f"Too many documents for the browser ({size}): the limit is {LIMITS['max_documents']} documents and "
            f"{LIMITS['max_words']:,} words. Use the command line (pip install copy-spotter) for larger sets."
        )
    if documents > LIMITS["warn_documents"] or words > LIMITS["warn_words"]:
        minutes = cost["seconds"] / 60
        duration = f"about {round(minutes)} min" if minutes >= 1.5 else f"about {round(cost['seconds'])} s"
        return "warn", (
            f"Large comparison ({size}): it may take {duration} and about {round(cost['memory_mb'])} MB of memory. "
            "Keep this tab open."
        )
    return "ok", ""


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


def _read(entries: list[tuple[str, Any]], progress: ProgressFn | None) -> tuple[list[Document], list[dict[str, str]]]:
    """Read the files; return the documents with words and the files left out, with the reason."""
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
    return documents, skipped


def analyze(
    files: Iterable[Sequence[Any]],
    *,
    block_size: int = MIN_BLOCK_SIZE,
    engine: str = "shingle",
    score: str = "coverage",
    thresholds: Iterable[float] = (5, 10, 15),
    progress: ProgressFn | None = None,
    notice: NoticeFn | None = None,
) -> dict[str, Any]:
    """Read and compare in-memory files.

    Args:
        files: ``(name, data)`` pairs. ``name`` is the path relative to the chosen folder, unique, and its extension
            gives the format; ``data`` is the file's content.
        block_size: See :func:`copy_spotter.compare_documents`; at least :data:`MIN_BLOCK_SIZE` here.
        engine: See :func:`copy_spotter.compare_documents`.
        score: See :meth:`copy_spotter.Results.to_html`.
        thresholds: See :meth:`copy_spotter.Results.to_html`.
        progress: Called as ``progress(stage, done, total)`` while files are read and pairs compared.
        notice: Called with a warning before a large comparison starts (see :func:`check_size`).

    Returns:
        On success ``{"html", "json", "csv", "names", "skipped", "version", "warning"}``. ``skipped`` lists
        ``{"name", "reason", "detail"}`` for files left out; ``warning`` is the large comparison warning or ``""``.
        When fewer than two documents are readable, the set is too large, or an option is invalid,
        ``{"error", "skipped"}`` instead.
    """
    if not isinstance(block_size, int) or block_size < MIN_BLOCK_SIZE:
        return {
            "error": f"The minimum match length must be at least {MIN_BLOCK_SIZE} words in the browser, "
            f"got {block_size}. Shorter runs are mostly common phrases and need much more memory.",
            "skipped": [],
        }
    entries = sorted(((str(name), data) for name, data in files), key=lambda entry: PurePosixPath(entry[0]).parts)
    if len(entries) > LIMITS["max_documents"]:  # refuse before spending time reading them
        return {"error": check_size(len(entries), 0)[1], "skipped": []}
    documents, skipped = _read(entries, progress)
    if len(documents) < 2:
        return {"error": f"Need at least two readable documents, found {len(documents)}.", "skipped": skipped}
    level, message = check_size(len(documents), sum(len(document.words) for document in documents))
    if level == "refuse":
        return {"error": message, "skipped": skipped}
    if level == "warn" and notice is not None:
        notice(message)
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
            "warning": message,
        }
    except ValueError as exc:
        return {"error": str(exc), "skipped": skipped}
