"""Single-page HTML report: every document and pair embedded as JSON, rendered by inline JavaScript."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from copy_spotter._options import DEFAULT_THRESHOLDS, ScoreMode
from copy_spotter._report import _render, _template

if TYPE_CHECKING:
    from copy_spotter._results import Results

DATA_VERSION = 1


def report_data(
    results: Results,
    meta: str = "",
    *,
    score: ScoreMode = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """Return the data embedded in the single page. This is the only place that defines its shape.

    ``{
        "version": 1,
        "meta": str,                      # one line describing the run
        "score_mode": "coverage" | "ratio",   # which score the page shows
        "thresholds": [t1, t2, t3],       # score color steps, in percent, increasing
        "documents": [                    # indexed by the "i" / "j" of each pair
            {"name": str, "text": str, "spans": [[start, end], ...]},
        ],
        "pairs": [
            {"i": int, "j": int, "ratio": float, "coverage_i": float, "coverage_j": float,
             "blocks": [[a, b, size], ...]},
        ],
    }``

    ``text`` is the document's display text and ``spans[k]`` the character range of its k-th word.
    A document may also have ``"excluded": [[start, size, reason], ...]``: word runs left out of the matching
    (``reason`` is ``"quote"``, ``"bibliography"``, ``"template"`` or ``"common"``), shown in grey.
    A block ``[a, b, size]`` means words ``a .. a+size-1`` of document ``i`` equal words ``b .. b+size-1``
    of document ``j``; blocks may be in any order on either side. ``coverage_i`` is the percentage of
    document ``i`` found in ``j``, ``coverage_j`` the reverse, ``ratio`` the symmetric score of the engine.
    Fields may be added; the page ignores fields it does not know.
    """
    documents: list[dict[str, Any]] = [
        {"name": doc.name, "text": doc.text, "spans": [list(span) for span in doc.spans]} for doc in results.documents
    ]
    for document, runs in zip(documents, results.excluded, strict=False):
        if runs:
            document["excluded"] = [[run.start, run.size, run.reason] for run in runs]
    return {
        "version": DATA_VERSION,
        "meta": meta,
        "score_mode": score,
        "thresholds": list(thresholds),
        "documents": documents,
        "pairs": [
            {
                "i": p.i,
                "j": p.j,
                "ratio": p.ratio,
                "coverage_i": p.coverage_i,
                "coverage_j": p.coverage_j,
                "blocks": [[m.a, m.b, m.size] for m in p.blocks],
            }
            for p in results.pairs
        ],
    }


def script_json(data: Any) -> str:
    """Serialize ``data`` as JSON that is safe inside an HTML ``<script>`` element."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def render_single(
    results: Results,
    meta: str = "",
    *,
    score: ScoreMode = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> str:
    """Return the self-contained report page (no external resources, works from ``file://``)."""
    data = report_data(results, meta, score=score, thresholds=thresholds)
    return _render(_template("single.html"), data=script_json(data), addon=_addon(data))


def _addon(data: dict[str, Any]) -> str:
    """Return the script of the optional features the report uses, or ``""`` (the page is then unchanged)."""
    if any("excluded" in document for document in data["documents"]):
        return _template("single_addon.html")
    return ""
