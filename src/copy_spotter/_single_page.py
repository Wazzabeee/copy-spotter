"""Single-page HTML report: every document and pair embedded as JSON, rendered by inline JavaScript."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, TextIO

from copy_spotter._options import DEFAULT_THRESHOLDS, ScoreMode
from copy_spotter._report import _PLACEHOLDER_RE, _template

if TYPE_CHECKING:
    from copy_spotter._compare import Pair
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
    A reference source has ``"reference": true``; references are never paired with each other.
    A block ``[a, b, size]`` means words ``a .. a+size-1`` of document ``i`` equal words ``b .. b+size-1``
    of document ``j``; blocks may be in any order on either side. ``coverage_i`` is the percentage of
    document ``i`` found in ``j``, ``coverage_j`` the reverse, ``ratio`` the symmetric score of the engine.
    Fields may be added; the page ignores fields it does not know.
    """
    return {
        **_header(meta, score, thresholds),
        "documents": [_document_record(results, k) for k in range(len(results.documents))],
        "pairs": [_pair_record(p) for p in results.pairs],
    }


def _header(meta: str, score: ScoreMode, thresholds: Sequence[float]) -> dict[str, Any]:
    return {"version": DATA_VERSION, "meta": meta, "score_mode": score, "thresholds": list(thresholds)}


def _document_record(results: Results, index: int) -> dict[str, Any]:
    doc = results.documents[index]
    record: dict[str, Any] = {"name": doc.name, "text": doc.text, "spans": [list(span) for span in doc.spans]}
    if index in results.references:
        record["reference"] = True
    runs = results.excluded[index] if index < len(results.excluded) else ()
    if runs:
        record["excluded"] = [[run.start, run.size, run.reason] for run in runs]
    return record


def _pair_record(p: Pair) -> dict[str, Any]:
    return {
        "i": p.i,
        "j": p.j,
        "ratio": p.ratio,
        "coverage_i": p.coverage_i,
        "coverage_j": p.coverage_j,
        "blocks": [[m.a, m.b, m.size] for m in p.blocks],
    }


def script_json(data: Any) -> str:
    """Serialize ``data`` as JSON that is safe inside an HTML ``<script>`` element."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def iter_script_json(
    results: Results,
    meta: str = "",
    *,
    score: ScoreMode = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> Iterator[str]:
    """Yield ``script_json(report_data(...))`` in chunks: one per document and one per pair.

    The header is dumped with empty ``documents`` and ``pairs`` lists (the last two keys, in this order), and each
    record is dumped alone in between. JSON separators and the escaping of ``&``, ``<`` and ``>`` work character by
    character, so the joined chunks are exactly the one-shot text.
    """
    head = script_json({**_header(meta, score, thresholds), "documents": [], "pairs": []})
    end = '"documents":[],"pairs":[]}'
    if not head.endswith(end):  # pragma: no cover - guards the key order that the slicing below relies on
        raise AssertionError("documents and pairs must be the last keys of the report data")
    yield head[: -len(end)] + '"documents":['
    for k in range(len(results.documents)):
        yield ("," if k else "") + script_json(_document_record(results, k))
    yield '],"pairs":['
    for k, p in enumerate(results.pairs):
        yield ("," if k else "") + script_json(_pair_record(p))
    yield "]}"


def _uses_addon(results: Results) -> bool:
    """Whether the report shows excluded passages or reference sources: the page then embeds single_addon.html."""
    return bool(results.references) or any(results.excluded)


def iter_single(
    results: Results,
    meta: str = "",
    *,
    score: ScoreMode = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> Iterator[str]:
    """Yield the report page in chunks; joined, they are :func:`render_single`."""
    template = _template("single.html")
    cursor = 0
    for placeholder in _PLACEHOLDER_RE.finditer(template):
        yield template[cursor : placeholder.start()]
        name = placeholder.group(1)
        if name == "data":
            yield from iter_script_json(results, meta, score=score, thresholds=thresholds)
        elif name == "addon":
            yield _template("single_addon.html") if _uses_addon(results) else ""
        else:  # pragma: no cover - single.html only has these two placeholders
            raise KeyError(name)
        cursor = placeholder.end()
    yield template[cursor:]


def write_single(
    results: Results,
    out: TextIO,
    meta: str = "",
    *,
    score: ScoreMode = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> None:
    """Write the report page to an open text file, document by document and pair by pair."""
    for chunk in iter_single(results, meta, score=score, thresholds=thresholds):
        out.write(chunk)


def render_single(
    results: Results,
    meta: str = "",
    *,
    score: ScoreMode = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> str:
    """Return the self-contained report page (no external resources, works from ``file://``)."""
    return "".join(iter_single(results, meta, score=score, thresholds=thresholds))
