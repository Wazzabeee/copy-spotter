"""Single-page HTML report: every document and pair embedded as JSON, rendered by inline JavaScript."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from copy_spotter._compare import PairResult
from copy_spotter._documents import Document
from copy_spotter._options import DEFAULT_THRESHOLDS
from copy_spotter._report import RESULTS_FILENAME, _render, _template

DATA_VERSION = 1


def report_data(
    names: Sequence[str],
    documents: Sequence[Document],
    pairs: Sequence[PairResult],
    meta: str = "",
    *,
    score_mode: str = "coverage",
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
    A block ``[a, b, size]`` means words ``a .. a+size-1`` of document ``i`` equal words ``b .. b+size-1``
    of document ``j``; blocks may be in any order on either side. ``coverage_i`` is the percentage of
    document ``i`` found in ``j``, ``coverage_j`` the reverse, ``ratio`` the symmetric score of the engine.
    Fields may be added; the page ignores fields it does not know.
    """
    return {
        "version": DATA_VERSION,
        "meta": meta,
        "score_mode": score_mode,
        "thresholds": list(thresholds),
        "documents": [
            {"name": name, "text": doc.text, "spans": [list(span) for span in doc.spans]}
            for name, doc in zip(names, documents, strict=True)
        ],
        "pairs": [
            {
                "i": p.i,
                "j": p.j,
                "ratio": p.score,
                "coverage_i": p.coverage_i,
                "coverage_j": p.coverage_j,
                "blocks": [[m.a, m.b, m.size] for m in p.blocks],
            }
            for p in pairs
        ],
    }


def script_json(data: Any) -> str:
    """Serialize ``data`` as JSON that is safe inside an HTML ``<script>`` element."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def render_single(
    names: Sequence[str],
    documents: Sequence[Document],
    pairs: Sequence[PairResult],
    meta: str = "",
    *,
    score_mode: str = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> str:
    """Return the self-contained report page (no external resources, works from ``file://``)."""
    data = report_data(names, documents, pairs, meta, score_mode=score_mode, thresholds=thresholds)
    return _render(_template("single.html"), data=script_json(data))


def write_single_report(
    out_dir: Path,
    names: Sequence[str],
    documents: Sequence[Document],
    pairs: Sequence[PairResult],
    meta: str = "",
    *,
    score_mode: str = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> Path:
    """Write the single-page report into ``out_dir`` and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RESULTS_FILENAME
    page = render_single(names, documents, pairs, meta, score_mode=score_mode, thresholds=thresholds)
    path.write_text(page, encoding="utf-8")
    return path
