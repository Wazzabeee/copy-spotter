"""Machine-readable exports of the comparison results: JSON (pairs with blocks) and CSV (one row per pair).

Field names are stable. New fields may be added in later versions; existing ones keep their name and meaning.
Pairs are sorted by their highest score in the chosen score mode (the larger coverage, or the ratio), highest
first. Word positions count the words copy-spotter extracted from a document (lowercase runs of letters and
digits), starting at 0.

JSON::

    {
        "version": 1,
        "copy_spotter_version": str,
        "engine": "shingle" | "difflib",       # matching engine used for the run
        "score_mode": "coverage" | "ratio",    # score used to sort the pairs and shown in the report
        "block_size": int,                     # minimum block size used for the run
        "documents": [{"index": int, "name": str, "word_count": int}, ...],
        "pairs": [
            {
                "document_1": str, "document_2": str,   # names, as in "documents"
                "index_1": int, "index_2": int,         # indexes into "documents"
                "coverage_1": float,                    # % of document 1 found in document 2
                "coverage_2": float,                    # % of document 2 found in document 1
                "ratio": float,                         # symmetric similarity of the engine, in percent
                "matched_words": int,                   # total size of the blocks
                "blocks": [{"start_1": int, "start_2": int, "size": int}, ...],
            },
            ...
        ],
    }

A block means words ``start_1 .. start_1 + size - 1`` of document 1 equal words ``start_2 ..`` of document 2.
Blocks are listed in the engine's order and may be out of order on either side.

CSV columns: ``document_1, document_2, coverage_1, coverage_2, ratio, matched_words, block_count``.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from copy_spotter import __version__
from copy_spotter.extract import Document
from copy_spotter.report import PairResult

EXPORT_VERSION = 1
CSV_FIELDS = ("document_1", "document_2", "coverage_1", "coverage_2", "ratio", "matched_words", "block_count")


def _sorted(pairs: Sequence[PairResult], score_mode: str) -> list[PairResult]:
    return sorted(pairs, key=lambda p: (-max(p.scores(score_mode)), p.i, p.j))


def _matched_words(pair: PairResult) -> int:
    return sum(m.size for m in pair.blocks)


def export_data(
    names: Sequence[str],
    documents: Sequence[Document],
    pairs: Sequence[PairResult],
    *,
    block_size: int,
    engine: str,
    score_mode: str = "coverage",
) -> dict[str, Any]:
    """Return the JSON export as a dict (see the module docstring for the shape)."""
    return {
        "version": EXPORT_VERSION,
        "copy_spotter_version": __version__,
        "engine": engine,
        "score_mode": score_mode,
        "block_size": block_size,
        "documents": [
            {"index": k, "name": name, "word_count": len(doc.words)}
            for k, (name, doc) in enumerate(zip(names, documents, strict=True))
        ],
        "pairs": [
            {
                "document_1": names[p.i],
                "document_2": names[p.j],
                "index_1": p.i,
                "index_2": p.j,
                "coverage_1": p.coverage_i,
                "coverage_2": p.coverage_j,
                "ratio": p.score,
                "matched_words": _matched_words(p),
                "blocks": [{"start_1": m.a, "start_2": m.b, "size": m.size} for m in p.blocks],
            }
            for p in _sorted(pairs, score_mode)
        ],
    }


def write_json(
    path: Path,
    names: Sequence[str],
    documents: Sequence[Document],
    pairs: Sequence[PairResult],
    *,
    block_size: int,
    engine: str,
    score_mode: str = "coverage",
) -> Path:
    """Write the JSON export to ``path`` (parent directories are created) and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = export_data(names, documents, pairs, block_size=block_size, engine=engine, score_mode=score_mode)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_csv(path: Path, names: Sequence[str], pairs: Sequence[PairResult], *, score_mode: str = "coverage") -> Path:
    """Write one CSV row per pair to ``path`` (parent directories are created) and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        for p in _sorted(pairs, score_mode):
            writer.writerow(
                [names[p.i], names[p.j], p.coverage_i, p.coverage_j, p.score, _matched_words(p), len(p.blocks)]
            )
    return path
