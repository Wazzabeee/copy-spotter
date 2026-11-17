"""Similarity scores and matching blocks between two word sequences."""

from __future__ import annotations

import difflib
from typing import NamedTuple


class Match(NamedTuple):
    """A run of identical words: words1[a:a+size] == words2[b:b+size]."""

    a: int
    b: int
    size: int


class Comparison(NamedTuple):
    """Result of comparing two word sequences."""

    score: float
    blocks: list[Match]


def compare(words1: list[str], words2: list[str], min_size: int = 2) -> Comparison:
    """Return the similarity percentage and the matching runs of at least ``min_size`` words."""
    matcher = difflib.SequenceMatcher(a=words1, b=words2)
    score = round(matcher.ratio() * 100, 3) if (words1 or words2) else 0.0
    min_size = max(min_size, 1)
    blocks = [Match(m.a, m.b, m.size) for m in matcher.get_matching_blocks() if m.size >= min_size]
    return Comparison(score, blocks)


def coverage(blocks: list[Match], len_a: int, len_b: int) -> tuple[float, float]:
    """Return the percentage of words of A found in B, and of B found in A.

    Only the words inside ``blocks`` count, so blocks shorter than the minimum block size (already
    filtered out by the matching engine) do not contribute. Overlapping blocks are counted once.
    """
    spans_a = [(m.a, m.a + m.size) for m in blocks]
    spans_b = [(m.b, m.b + m.size) for m in blocks]
    return _percent(_covered(spans_a), len_a), _percent(_covered(spans_b), len_b)


def _covered(spans: list[tuple[int, int]]) -> int:
    """Return the number of positions in the union of half-open ``(start, end)`` spans."""
    total = 0
    end_so_far = 0
    for start, end in sorted(spans):
        if end > end_so_far:
            total += end - max(start, end_so_far)
            end_so_far = end
    return total


def _percent(part: int, whole: int) -> float:
    return round(min(part, whole) / whole * 100, 3) if whole > 0 else 0.0


def difflib_overlap(words1: list[str], words2: list[str]) -> float:
    """Return the difflib similarity ratio between two word sequences, as a percentage."""
    return compare(words1, words2).score
