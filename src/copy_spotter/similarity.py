"""Similarity scores and matching blocks between two word sequences."""

from __future__ import annotations

import difflib
import heapq
import re
from collections.abc import Callable
from typing import Literal, NamedTuple, get_args

Engine = Literal["shingle", "difflib"]
ENGINES: tuple[Engine, ...] = get_args(Engine)
DEFAULT_ENGINE: Engine = "shingle"


class Match(NamedTuple):
    """A run of identical words: words1[a:a+size] == words2[b:b+size]."""

    a: int
    b: int
    size: int


class Comparison(NamedTuple):
    """Result of comparing two word sequences."""

    score: float
    blocks: list[Match]


def compare(words1: list[str], words2: list[str], min_size: int = 2, engine: Engine = DEFAULT_ENGINE) -> Comparison:
    """Return the similarity percentage and the matching runs of at least ``min_size`` words.

    ``engine`` selects the matching algorithm: ``"shingle"`` (default) or ``"difflib"`` (legacy).
    """
    return _ENGINE_FUNCTIONS[engine](words1, words2, min_size)


def compare_difflib(words1: list[str], words2: list[str], min_size: int = 2) -> Comparison:
    """Legacy engine: ``difflib.SequenceMatcher``, which follows a single in-order alignment."""
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


def compare_shingle(words1: list[str], words2: list[str], min_size: int = 2) -> Comparison:
    """Shingle engine: find every shared run of at least ``max(min_size, 2)`` words, in any order.

    Word n-grams of ``words2`` are indexed, each shared n-gram seeds a maximal run of identical words,
    and runs are kept longest first (greedy string tiling) so that blocks never overlap on either side.
    Blocks are sorted by position in ``words1``; their order in ``words2`` is arbitrary. The score is
    ``2 * matched words / total words * 100``, like the difflib ratio, counting the returned blocks only.
    """
    n = max(min_size, 2)
    ids: dict[str, int] = {}
    seq1 = [ids.setdefault(w, len(ids)) for w in words1]
    seq2 = [ids.setdefault(w, len(ids)) for w in words2]
    blocks = _tile(seq1, seq2, n)
    total = len(seq1) + len(seq2)
    score = round(2 * sum(m.size for m in blocks) / total * 100, 3) if total else 0.0
    return Comparison(score, blocks)


def _run_length(seq1: list[int], seq2: list[int], i: int, j: int, k: int) -> int:
    """Return the length of the run of identical items at ``seq1[i]`` and ``seq2[j]``, known to be at least ``k``."""
    limit = min(len(seq1) - i, len(seq2) - j)
    step = 64
    while k + step <= limit and seq1[i + k : i + k + step] == seq2[j + k : j + k + step]:
        k += step  # compare whole slices first: much faster than item by item on long runs
    while k < limit and seq1[i + k] == seq2[j + k]:
        k += 1
    return k


def _maximal_runs(seq1: list[int], seq2: list[int], n: int) -> list[tuple[int, int, int]]:
    """Return every maximal run ``(-size, a, b)`` of at least ``n`` identical items."""
    # n-gram -> word before it (-1 at the start) -> positions in seq2. Grouping by the previous word
    # skips runs that are not maximal without looking at them, which keeps repetitive texts fast.
    index: dict[tuple[int, ...], dict[int, list[int]]] = {}
    for j in range(len(seq2) - n + 1):
        before = seq2[j - 1] if j else -1
        index.setdefault(tuple(seq2[j : j + n]), {}).setdefault(before, []).append(j)

    len1, len2 = len(seq1), len(seq2)
    runs: list[tuple[int, int, int]] = []
    for i in range(len(seq1) - n + 1):
        groups = index.get(tuple(seq1[i : i + n]))
        if groups is None:
            continue
        before = seq1[i - 1] if i else -2
        after = seq1[i + n] if i + n < len1 else -3
        for prev, positions in groups.items():
            if prev == before:
                continue  # both runs extend one word to the left: covered by an earlier start
            for j in positions:
                if j + n < len2 and seq2[j + n] != after:
                    runs.append((-n, i, j))  # fast path: most runs stop right after the seed n-gram
                else:
                    runs.append((-_run_length(seq1, seq2, i, j, n), i, j))
    return runs


def _tile(seq1: list[int], seq2: list[int], n: int) -> list[Match]:
    """Pick non-overlapping runs of at least ``n`` items, longest first."""
    heap = _maximal_runs(seq1, seq2, n)
    heapq.heapify(heap)
    used1 = bytearray(len(seq1))
    used2 = bytearray(len(seq2))
    free_run = re.compile(rb"\x00{%d,}" % n)
    blocks = []
    while heap:
        neg_size, a, b = heapq.heappop(heap)
        size = -neg_size
        span1 = used1[a : a + size]
        span2 = used2[b : b + size]
        taken1 = span1.count(1)
        taken2 = span2.count(1)
        if not taken1 and not taken2:
            blocks.append(Match(a, b, size))
            used1[a : a + size] = b"\x01" * size
            used2[b : b + size] = b"\x01" * size
            continue
        if size - max(taken1, taken2) < n:
            continue  # not enough free words left for a block
        # Part of the run is already used: put back its free stretches that are still long enough.
        both = (int.from_bytes(span1, "big") | int.from_bytes(span2, "big")).to_bytes(size, "big")
        for free in free_run.finditer(both):
            start, end = free.span()
            heapq.heappush(heap, (start - end, a + start, b + start))
    blocks.sort()
    return blocks


_ENGINE_FUNCTIONS: dict[Engine, Callable[[list[str], list[str], int], Comparison]] = {
    "shingle": compare_shingle,
    "difflib": compare_difflib,
}


def difflib_overlap(words1: list[str], words2: list[str]) -> float:
    """Return the difflib similarity ratio between two word sequences, as a percentage."""
    return compare(words1, words2, engine="difflib").score
