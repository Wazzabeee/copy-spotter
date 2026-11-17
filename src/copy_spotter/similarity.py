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


def difflib_overlap(words1: list[str], words2: list[str]) -> float:
    """Return the difflib similarity ratio between two word sequences, as a percentage."""
    return compare(words1, words2).score
