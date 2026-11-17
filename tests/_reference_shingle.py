"""Test-only reference: the shingle engine as it was before the shared index, kept verbatim as an oracle.

``ShingleIndex`` in ``copy_spotter.similarity`` must return exactly the same blocks and scores.
"""

from __future__ import annotations

import heapq
import re

from copy_spotter.similarity import Comparison, Match

_MAX_SEED_OCCURRENCES = 64  # n-grams more frequent than this in a document do not seed runs


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
    """Return the maximal runs ``(-size, a, b)`` of at least ``n`` items whose first n-gram is not too frequent."""
    # n-gram -> word before it (-1 at the start) -> positions in seq2. Grouping by the previous word
    # skips runs that are not maximal without looking at them, which keeps repetitive texts fast.
    index: dict[tuple[int, ...], dict[int, list[int]]] = {}
    counts: dict[tuple[int, ...], int] = {}
    for j in range(len(seq2) - n + 1):
        key = tuple(seq2[j : j + n])
        before = seq2[j - 1] if j else -1
        index.setdefault(key, {}).setdefault(before, []).append(j)
        counts[key] = counts.get(key, 0) + 1
    for key, count in counts.items():
        if count > _MAX_SEED_OCCURRENCES:
            del index[key]  # would make the number of runs quadratic: left to _tile_exact

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
    used1 = bytearray(len(seq1))
    used2 = bytearray(len(seq2))
    # Repetitive text can have a quadratic number of runs, so the heap only gets runs longer than n
    # seeded by n+1-grams that are not too frequent. A linear scan then matches every free n-gram left.
    blocks = _tile_longest_first(seq1, seq2, n + 1, used1, used2)
    blocks += _tile_exact(seq1, seq2, n, used1, used2)
    blocks.sort()
    return blocks


def _tile_longest_first(seq1: list[int], seq2: list[int], n: int, used1: bytearray, used2: bytearray) -> list[Match]:
    """Pick non-overlapping runs of at least ``n`` items, longest first, and mark them as used."""
    heap = _maximal_runs(seq1, seq2, n)
    heapq.heapify(heap)
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
    return blocks


def _tile_exact(seq1: list[int], seq2: list[int], n: int, used1: bytearray, used2: bytearray) -> list[Match]:
    """Match each free n-gram of ``seq1``, in order, to its first free occurrence in ``seq2``, then extend it."""
    index: dict[tuple[int, ...], list[int]] = {}
    for j in range(len(seq2) - n + 1):
        if 1 not in used2[j : j + n]:
            index.setdefault(tuple(seq2[j : j + n]), []).append(j)
    cursor = dict.fromkeys(index, 0)  # positions before the cursor are used for good: never look at them again
    blocks = []
    for i in range(len(seq1) - n + 1):
        key = tuple(seq1[i : i + n])
        positions = index.get(key)
        if positions is None or 1 in used1[i : i + n]:
            continue
        k = cursor[key]
        while k < len(positions) and 1 in used2[positions[k] : positions[k] + n]:
            k += 1
        if k < len(positions):
            j = positions[k]
            size = n
            while (
                i + size < len(seq1)
                and j + size < len(seq2)
                and seq1[i + size] == seq2[j + size]
                and not used1[i + size]
                and not used2[j + size]
            ):
                size += 1
            blocks.append(Match(i, j, size))
            used1[i : i + size] = b"\x01" * size
            used2[j : j + size] = b"\x01" * size
            k += 1
        cursor[key] = k
    return blocks
