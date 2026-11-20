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
        "thresholds": [float, float, float],   # score color steps of the HTML report, in percent
        "options": {...},                      # only when matching options were on, see below
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

``options`` lists the matching options that were turned on and is left out when there are none:
``"normalize": ["accents"]`` (accents folded), ``"stopwords": int`` (number of stopwords left out of the
matching; ``word_count`` and word positions then count the remaining words only), ``"ignore_quotes": true`` and
``"ignore_bibliography": true``, ``"templates": [str]`` (names of the template documents) and
``"ignore_common": float`` (the percentage). When passages were excluded from the matching, each document also has
``"excluded_words": int`` and ``"excluded": [{"start": int, "size": int, "reason": str}]``, the reason being
``"quote"``, ``"bibliography"``, ``"template"`` or ``"common"``: excluded words never match but still count in
``word_count`` and the coverages.

CSV columns: ``document_1, document_2, coverage_1, coverage_2, ratio, matched_words, block_count``.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from copy_spotter._options import DEFAULT_THRESHOLDS, ScoreMode
from copy_spotter._version import __version__

if TYPE_CHECKING:
    from copy_spotter._results import Results

EXPORT_VERSION = 1
CSV_FIELDS = ("document_1", "document_2", "coverage_1", "coverage_2", "ratio", "matched_words", "block_count")


def export_data(
    results: Results, *, score: ScoreMode = "coverage", thresholds: Sequence[float] = DEFAULT_THRESHOLDS
) -> dict[str, Any]:
    """Return the JSON export as a dict (see the module docstring for the shape)."""
    names = [document.name for document in results.documents]
    data: dict[str, Any] = {
        "version": EXPORT_VERSION,
        "copy_spotter_version": __version__,
        "engine": results.engine,
        "score_mode": score,
        "block_size": results.block_size,
        "thresholds": list(thresholds),
    }
    if results.options:
        data["options"] = dict(results.options)
    documents = [
        {"index": k, "name": document.name, "word_count": len(document.words)}
        for k, document in enumerate(results.documents)
    ]
    for document, runs in zip(documents, results.excluded, strict=False):
        document["excluded_words"] = sum(run.size for run in runs)
        document["excluded"] = [{"start": run.start, "size": run.size, "reason": run.reason} for run in runs]
    return data | {
        "documents": documents,
        "pairs": [
            {
                "document_1": names[p.i],
                "document_2": names[p.j],
                "index_1": p.i,
                "index_2": p.j,
                "coverage_1": p.coverage_i,
                "coverage_2": p.coverage_j,
                "ratio": p.ratio,
                "matched_words": p.matched_words,
                "blocks": [{"start_1": m.a, "start_2": m.b, "size": m.size} for m in p.blocks],
            }
            for p in results.ranked(score)
        ],
    }


def export_json(
    results: Results, *, score: ScoreMode = "coverage", thresholds: Sequence[float] = DEFAULT_THRESHOLDS
) -> str:
    """Return the JSON export as indented text ending with a newline."""
    return json.dumps(export_data(results, score=score, thresholds=thresholds), ensure_ascii=False, indent=2) + "\n"


def export_csv(results: Results, *, score: ScoreMode = "coverage") -> str:
    """Return the CSV export: a header and one row per pair, each ending with ``\\r\\n``."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_FIELDS)
    names = [document.name for document in results.documents]
    for p in results.ranked(score):
        writer.writerow([names[p.i], names[p.j], p.coverage_i, p.coverage_j, p.ratio, p.matched_words, len(p.blocks)])
    return out.getvalue()
