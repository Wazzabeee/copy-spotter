"""Similarity scores and matching blocks between two word sequences."""

from __future__ import annotations

import difflib
import gc
import heapq
import re
from array import array
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from itertools import combinations, count
from typing import Literal, NamedTuple, get_args

Engine = Literal["shingle", "difflib"]
ENGINES: tuple[Engine, ...] = get_args(Engine)
DEFAULT_ENGINE: Engine = "shingle"
_MAX_SEED_OCCURRENCES = 64  # n-grams more frequent than this in a document do not seed runs


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

    Each shared n-gram seeds a maximal run of identical words, and runs are kept longest first (greedy
    string tiling) so that blocks never overlap on either side. Blocks are sorted by position in ``words1``;
    their order in ``words2`` is arbitrary. The score is ``2 * matched words / total words * 100``, like the
    difflib ratio, counting the returned blocks only. To compare many documents, use :func:`compare_all` or
    :class:`ShingleIndex`, which index each document once instead of once per pair: calling this function
    for every pair is several times slower.
    """
    return ShingleIndex([words1, words2], min_size).compare(0, 1)


def compare_all(
    texts: Sequence[Sequence[str]], min_size: int = 2, engine: Engine = DEFAULT_ENGINE
) -> Iterator[Comparison]:
    """Compare every pair of ``texts``, yielding one result per pair in ``itertools.combinations`` order.

    ``compare_all(texts)`` yields the same results as ``compare(texts[i], texts[j])`` for each ``i < j``,
    but the shingle engine indexes every document once for the whole corpus instead of once per pair.
    """
    pairs = combinations(range(len(texts)), 2)
    if engine == "shingle":
        index = ShingleIndex(texts, min_size)
        for i, j in pairs:
            yield index.compare(i, j)
    else:
        for i, j in pairs:
            yield compare(list(texts[i]), list(texts[j]), min_size, engine)


class ShingleIndex:
    """Word n-grams of a corpus, indexed once, to run the shingle engine on any pair of its documents.

    Words and n-grams get corpus-wide integer ids, and each document keeps the positions of its n-grams
    (for the final scan) and of its (n+1)-grams (seeds of runs longer than n). Comparing two documents
    then only looks at the n-grams they share. ``compare(i, j)`` returns exactly what the engine returns
    for ``texts[i]`` and ``texts[j]``. The index is made of plain dicts, lists and arrays: no threads or
    processes, and it can be pickled.
    """

    def __init__(self, texts: Sequence[Sequence[str]], min_size: int = 2) -> None:
        n = max(min_size, 2)
        self.n = n
        # Ids are handed out in C by defaultdict(count().__next__) and n-grams are built by zip(): indexing a
        # document is linear, and cheap enough that the two-document wrapper compare_shingle() stays usable.
        word_ids: defaultdict[str, int] = defaultdict(count().__next__)
        gram_ids: defaultdict[tuple[int, ...], int] = defaultdict(count().__next__)  # exact: no hash collisions
        seed_ids: defaultdict[tuple[int, int], int] = defaultdict(count().__next__)  # (n-gram id, next word)
        self._seqs: list[array[int]] = []  # word ids
        self._grams: list[array[int]] = []  # n-gram id at each position
        self._starts: list[dict[int, list[int]]] = []  # n-gram id -> positions
        self._seeds: list[dict[int, list[int]]] = []  # (n+1)-gram id -> positions
        with _gc_paused():
            for text in texts:
                seq = list(map(word_ids.__getitem__, text))
                grams = list(map(gram_ids.__getitem__, zip(*(seq[k:] for k in range(n)), strict=False)))
                seeds = list(map(seed_ids.__getitem__, zip(grams, seq[n:], strict=False)))
                self._seqs.append(array("i", seq))
                self._grams.append(array("i", grams))
                self._starts.append(_positions(grams))
                self._seeds.append(_positions(seeds))

    def __len__(self) -> int:
        return len(self._seqs)

    def compare(self, i: int, j: int) -> Comparison:
        """Compare documents ``i`` (the ``words1`` side) and ``j`` (the ``words2`` side) of the corpus."""
        with _gc_paused():
            return self._compare(i, j)

    def _compare(self, i: int, j: int) -> Comparison:
        seq1, seq2 = self._seqs[i], self._seqs[j]
        if self._starts[i].keys().isdisjoint(self._starts[j].keys()):
            return Comparison(0.0, [])  # no shared n-gram: no block, whatever the lengths
        used1 = bytearray(len(seq1))
        used2 = bytearray(len(seq2))
        # Repetitive text can have a quadratic number of runs, so the heap only gets runs longer than n
        # seeded by n+1-grams that are not too frequent. A linear scan then matches every free n-gram left.
        blocks = _tile_longest_first(self._runs(i, j), self.n + 1, used1, used2)
        blocks += self._tile_exact(i, j, used1, used2)
        blocks.sort()
        total = len(seq1) + len(seq2)
        return Comparison(round(2 * sum(m.size for m in blocks) / total * 100, 3), blocks)

    def _runs(self, i: int, j: int) -> list[tuple[int, int, int]]:
        """Return the maximal runs ``(-size, a, b)`` of at least n+1 items seeded by a not too frequent n+1-gram."""
        m = self.n + 1
        seq1, seq2 = self._seqs[i], self._seqs[j]
        seeds1, seeds2 = self._seeds[i], self._seeds[j]
        len1, len2 = len(seq1), len(seq2)
        max_occurrences = _MAX_SEED_OCCURRENCES
        runs: list[tuple[int, int, int]] = []
        for gram in seeds1.keys() & seeds2.keys():
            positions = seeds2[gram]
            if len(positions) > max_occurrences:
                continue  # would make the number of runs quadratic: left to _tile_exact
            for a in seeds1[gram]:
                before = seq1[a - 1] if a else -1
                after = seq1[a + m] if a + m < len1 else -1
                for b in positions:
                    if b and seq2[b - 1] == before:
                        continue  # both runs extend one word to the left: covered by an earlier start
                    if b + m < len2 and seq2[b + m] != after:
                        runs.append((-m, a, b))  # fast path: most runs stop right after the seed n-gram
                    else:
                        runs.append((-_run_length(seq1, seq2, a, b, m), a, b))
        return runs

    def _tile_exact(self, i: int, j: int, used1: bytearray, used2: bytearray) -> list[Match]:
        """Match each free n-gram of document i, in order, to its first free occurrence in j, then extend it."""
        n = self.n
        seq1, seq2 = self._seqs[i], self._seqs[j]
        starts1, starts2 = self._starts[i], self._starts[j]
        grams1 = self._grams[i]
        len1, len2 = len(seq1), len(seq2)
        cursor: dict[int, int] = {}  # positions before the cursor are used for good: never look at them again
        blocks = []
        for a in sorted(a for gram in starts1.keys() & starts2.keys() for a in starts1[gram]):
            if 1 in used1[a : a + n]:
                continue
            gram = grams1[a]
            positions = starts2[gram]
            k = cursor.get(gram, 0)
            while k < len(positions) and 1 in used2[positions[k] : positions[k] + n]:
                k += 1
            if k < len(positions):
                b = positions[k]
                size = n
                while (
                    a + size < len1
                    and b + size < len2
                    and seq1[a + size] == seq2[b + size]
                    and not used1[a + size]
                    and not used2[b + size]
                ):
                    size += 1
                blocks.append(Match(a, b, size))
                used1[a : a + size] = b"\x01" * size
                used2[b : b + size] = b"\x01" * size
                k += 1
            cursor[gram] = k
        return blocks


@contextmanager
def _gc_paused() -> Iterator[None]:
    """Pause the cyclic garbage collector, which the engine's many small acyclic objects would keep waking up.

    Restored on exit, even on error, and never held across a ``yield`` to the caller (about 15% faster).
    """
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if enabled:
            gc.enable()


def _positions(ids: list[int]) -> dict[int, list[int]]:
    """Return the positions of each id in ``ids``, in increasing order."""
    positions: dict[int, list[int]] = {}
    for k, key in enumerate(ids):
        if key in positions:
            positions[key].append(k)
        else:
            positions[key] = [k]
    return positions


def _run_length(seq1: array[int], seq2: array[int], i: int, j: int, k: int) -> int:
    """Return the length of the run of identical items at ``seq1[i]`` and ``seq2[j]``, known to be at least ``k``."""
    limit = min(len(seq1) - i, len(seq2) - j)
    step = 64
    while k + step <= limit and seq1[i + k : i + k + step] == seq2[j + k : j + k + step]:
        k += step  # compare whole slices first: much faster than item by item on long runs
    while k < limit and seq1[i + k] == seq2[j + k]:
        k += 1
    return k


def _tile_longest_first(heap: list[tuple[int, int, int]], n: int, used1: bytearray, used2: bytearray) -> list[Match]:
    """Pick non-overlapping runs ``(-size, a, b)`` of at least ``n`` items, longest first, and mark them as used."""
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


_ENGINE_FUNCTIONS: dict[Engine, Callable[[list[str], list[str], int], Comparison]] = {
    "shingle": compare_shingle,
    "difflib": compare_difflib,
}


def difflib_overlap(words1: list[str], words2: list[str]) -> float:
    """Return the difflib similarity ratio between two word sequences, as a percentage."""
    return compare(words1, words2, engine="difflib").score
