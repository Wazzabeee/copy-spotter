"""Rendering options shared by the reports and exports, and the checks of user supplied values."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, get_args

ScoreMode = Literal["coverage", "ratio"]
"""``coverage``: % of each document found in the other (asymmetric); ``ratio``: symmetric score of the pair."""

ReportLayout = Literal["single", "pages"]
"""``single``: one self-contained HTML file; ``pages``: a summary page plus one page per pair."""

Thresholds = tuple[float, float, float]

SCORE_MODES: tuple[ScoreMode, ...] = get_args(ScoreMode)
REPORT_LAYOUTS: tuple[ReportLayout, ...] = get_args(ReportLayout)
DEFAULT_THRESHOLDS: Thresholds = (5.0, 10.0, 15.0)


def check_score(score: str) -> ScoreMode:
    """Return ``score`` if it is a valid score mode, else raise ``ValueError``."""
    for mode in SCORE_MODES:
        if score == mode:
            return mode
    raise ValueError(f"score must be one of {', '.join(SCORE_MODES)}, got {score!r}")


def check_thresholds(thresholds: Iterable[float]) -> Thresholds:
    """Return ``thresholds`` as three floats, or raise ``ValueError`` unless they increase within 0 and 100."""
    values = tuple(float(value) for value in thresholds)
    if len(values) != 3:
        raise ValueError(f"expected three thresholds, got {len(values)}")
    low, medium, high = values
    if not 0 <= low < medium < high <= 100:
        raise ValueError(f"thresholds must be increasing percentages between 0 and 100, got {values}")
    return low, medium, high


def check_block_size(block_size: int) -> int:
    """Return ``block_size``, or raise ``ValueError`` if it is below 1."""
    if block_size < 1:
        raise ValueError(f"block_size must be at least 1, got {block_size}")
    return block_size
