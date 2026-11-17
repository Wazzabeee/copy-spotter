from __future__ import annotations

import pytest

from copy_spotter._errors import CopySpotterError, DocumentReadError, UnsupportedFormatError
from copy_spotter._options import (
    DEFAULT_THRESHOLDS,
    REPORT_LAYOUTS,
    SCORE_MODES,
    check_block_size,
    check_score,
    check_thresholds,
)


def test_option_values() -> None:
    assert SCORE_MODES == ("coverage", "ratio")
    assert REPORT_LAYOUTS == ("single", "pages")
    assert check_thresholds(DEFAULT_THRESHOLDS) == DEFAULT_THRESHOLDS


@pytest.mark.parametrize("score", ["coverage", "ratio"])
def test_check_score_accepts_known_modes(score: str) -> None:
    assert check_score(score) == score


def test_check_score_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="coverage, ratio"):
        check_score("words")


def test_check_thresholds_returns_floats() -> None:
    result = check_thresholds([0, 50, 100])
    assert result == (0.0, 50.0, 100.0)
    assert all(isinstance(value, float) for value in result)


@pytest.mark.parametrize("thresholds", [(1, 2), (1, 2, 3, 4), (5, 4, 3), (5, 5, 6), (-1, 2, 3), (1, 2, 101)])
def test_check_thresholds_rejects_invalid_values(thresholds: tuple[float, ...]) -> None:
    with pytest.raises(ValueError):
        check_thresholds(thresholds)


def test_check_block_size() -> None:
    assert check_block_size(1) == 1
    with pytest.raises(ValueError, match="at least 1"):
        check_block_size(0)


def test_error_hierarchy() -> None:
    assert issubclass(UnsupportedFormatError, CopySpotterError)
    assert issubclass(UnsupportedFormatError, ValueError)
    assert issubclass(DocumentReadError, CopySpotterError)
