"""Passages left out of the matching: quotations, bibliographies, template text and passages common to many documents.

An excluded passage stays in the document and in the report (shown in grey) but its words never match: before
comparing, each excluded word is replaced with a token unique to its document and position. Blocks therefore
stop at excluded words and never contain one, word positions do not move, and scores keep counting every word
of the document, so excluding passages can only lower a score.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from typing import Literal, NamedTuple

from copy_spotter.similarity import ShingleIndex

ExclusionReason = Literal["quote", "bibliography", "template", "common"]
"""Why words were left out: inside quotation marks, in the bibliography at the end of the document, found in a
template (such as the assignment prompt), or shared by too many documents."""

TEMPLATE_MIN_WORDS = 4
"""Minimum length of a passage shared with a template to exclude it: shorter runs ("of the", "it is a") are
everyday phrases, and excluding them would cut real copied passages into pieces."""


class Excluded(NamedTuple):
    """A run of words left out of the matching: words ``start .. start + size - 1`` of a document."""

    start: int
    size: int
    reason: ExclusionReason


# Quotation marks: opening mark -> the marks that close it. Single quotes are left out on purpose: the same
# characters are apostrophes ("don't", "l'eleve"), so they cannot be paired reliably.
_QUOTE_PAIRS = {
    '"': '"”',
    "“": '”"',  # English
    "„": "“”",  # German and Polish open low
    "«": "»",  # French and many other languages
    "»": "«",  # reversed guillemets (German, Danish)
    "「": "」",  # CJK corner brackets
    "『": "』",
}
# Where a paragraph ends: a blank line, or (docx, odt and rtf text, where paragraphs are separated by a single
# line break) a line break after the end of a sentence. A line break inside a sentence is a hard wrap.
_PARAGRAPH_BREAK_RE = re.compile(r"\n[^\S\n]*\n")
_SENTENCE_END_RE = re.compile(r"[.!?:;\u2026][^\S\n]*$")


def quote_ranges(text: str) -> list[tuple[int, int]]:
    """Return the ``(start, end)`` character ranges of the quotations in ``text``, marks included.

    Only outermost quotations count (a quote inside a quote is part of it). A quotation must close in the
    paragraph where it opens: an unmatched mark is ignored, so one stray mark cannot exclude the rest of the
    document. A paragraph ends at a blank line, or at a line break that follows the end of a sentence (word
    processors separate paragraphs with a single line break); other line breaks are hard wraps.
    """
    ranges: list[tuple[int, int]] = []
    open_at = -1
    closers = ""
    for index, char in enumerate(text):
        if open_at >= 0:
            if char in closers:
                ranges.append((open_at, index + 1))
                open_at = -1
            elif char == "\n" and (
                _PARAGRAPH_BREAK_RE.match(text, index) or _SENTENCE_END_RE.search(text, open_at + 1, index)
            ):
                open_at = -1  # unclosed at the end of the paragraph: not a quotation
        elif char in _QUOTE_PAIRS:
            open_at, closers = index, _QUOTE_PAIRS[char]
    return ranges


# Headings of a bibliography, in English, French, Spanish, German, Italian and Portuguese.
_BIBLIOGRAPHY_HEADINGS = (
    r"references|reference list|bibliography|works cited|works consulted|literature cited|sources|sources cited"
    r"|r[eé]f[eé]rences(?: bibliographiques)?|bibliographie|webographie"
    r"|referencias(?: bibliogr[aá]ficas)?|bibliograf[ií]a|obras citadas|fuentes"
    r"|literaturverzeichnis|literatur|quellen|quellenverzeichnis"
    r"|bibliografia|riferimenti bibliografici|refer[eê]ncias(?: bibliogr[aá]ficas)?"
)
# The heading starts a line, after an optional section number ("7.", "IV.", "7.1"), and either ends the line or
# (PDF text, where the next line may have been joined to it) is directly followed by a first entry that looks
# like a reference: "[1]", "1. " or "Surname, ".
_BIBLIOGRAPHY_RE = re.compile(
    rf"^[^\S\n]*(?:(?:\d+(?:\.\d+)*|(?-i:[IVXLC]+))\.?[^\S\n]+)?(?:{_BIBLIOGRAPHY_HEADINGS})[^\S\n]*:?"
    r"(?:[^\S\n]*$|(?=[^\S\n]+(?:\[\d|\d+\.\s|(?-i:[A-Z])[\w'-]+,\s)))",
    re.IGNORECASE | re.MULTILINE,
)
_BIBLIOGRAPHY_MIN_POSITION = 0.3  # a heading in the first 30% of the text is a title or a table of contents


def bibliography_start(text: str) -> int | None:
    """Return where the bibliography of ``text`` starts (its heading), or ``None`` if there is none.

    The bibliography is the text from the last bibliography heading (such as "References", "Works cited" or
    "Bibliographie" on a line of its own) to the end. A heading in the first 30% of the text is ignored.
    """
    matches = list(_BIBLIOGRAPHY_RE.finditer(text))
    if not matches:
        return None
    start = matches[-1].start()
    start += len(text[start:]) - len(text[start:].lstrip())
    return start if start >= _BIBLIOGRAPHY_MIN_POSITION * len(text) else None


def words_in(spans: Sequence[tuple[int, int]], ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return the ``(start, size)`` runs of words whose span lies entirely inside one of the character ``ranges``."""
    runs: list[tuple[int, int]] = []
    starts = [span[0] for span in spans]
    for begin, end in sorted(ranges):
        first = bisect_left(starts, begin)
        last = first
        while last < len(spans) and spans[last][1] <= end:
            last += 1
        if last > first:
            runs.append((first, last - first))
    return runs


def merge(excluded: Iterable[Excluded]) -> tuple[Excluded, ...]:
    """Sort runs by position and drop the words already covered by an earlier run (the earlier reason wins)."""
    merged: list[Excluded] = []
    next_free = 0
    for run in sorted(excluded):
        start = max(run.start, next_free)
        stop = run.start + run.size
        if start < stop:
            merged.append(Excluded(start, stop - start, run.reason))
            next_free = stop
    return tuple(merged)


def find_exclusions(
    text: str, spans: Sequence[tuple[int, int]], *, quotes: bool, bibliography: bool
) -> tuple[Excluded, ...]:
    """Return the runs of words of a document to leave out of the matching, sorted and non-overlapping."""
    found: list[Excluded] = []
    if quotes:
        found += [Excluded(start, size, "quote") for start, size in words_in(spans, quote_ranges(text))]
    if bibliography:
        start = bibliography_start(text)
        if start is not None:
            found += [Excluded(s, n, "bibliography") for s, n in words_in(spans, [(start, len(text))])]
    return merge(found)


def template_runs(
    words: Sequence[Sequence[str]], templates: Sequence[Sequence[str]], min_words: int = TEMPLATE_MIN_WORDS
) -> list[list[tuple[int, int]]]:
    """Return, for each word list, the ``(start, size)`` runs of at least ``min_words`` words found in a template.

    Runs are found with the shingle engine, in any order, against every template.
    """
    if not templates:
        return [[] for _ in words]
    index = ShingleIndex([*templates, *words], min_words)
    found = []
    for k in range(len(words)):
        runs = []
        for t in range(len(templates)):
            runs += [(m.a, m.size) for m in index.compare(len(templates) + k, t).blocks if m.size >= min_words]
        found.append(runs)
    return found


def common_runs(
    lengths: Sequence[int], matches: Iterable[tuple[int, int, Iterable[tuple[int, int, int]]]], min_documents: int
) -> list[list[tuple[int, int]]]:
    """Return, for each document, the ``(start, size)`` runs of words found in at least ``min_documents`` documents.

    Args:
        lengths: The number of words of each document.
        matches: ``(i, j, blocks)`` for each compared pair, ``blocks`` being ``(a, b, size)`` matches between
            documents ``i`` and ``j``. Blocks of one pair never overlap, so a word counts each other document once.
        min_documents: How many documents, the document itself included, must contain a word.
    """
    counts = [[0] * n for n in lengths]
    for i, j, blocks in matches:
        for a, b, size in blocks:
            for k in range(size):
                counts[i][a + k] += 1
                counts[j][b + k] += 1
    runs: list[list[tuple[int, int]]] = []
    for doc_counts in counts:
        doc_runs: list[tuple[int, int]] = []
        start = -1
        for position, count in enumerate([*doc_counts, -1]):  # the sentinel closes a run at the end
            if count >= 0 and count + 1 >= min_documents:
                start = position if start < 0 else start
            elif start >= 0:
                doc_runs.append((start, position - start))
                start = -1
        runs.append(doc_runs)
    return runs


def masked_words(words: Sequence[str], document: int, excluded: Iterable[Excluded]) -> list[str]:
    """Return ``words`` with every excluded word replaced by a token that matches no other word anywhere.

    Words are runs of letters and digits, so a token starting with ``"\\x00"`` can never equal one.
    """
    masked = list(words)
    for run in excluded:
        for position in range(run.start, run.start + run.size):
            masked[position] = f"\x00{document}:{position}"
    return masked


def excluded_word_count(excluded: Iterable[Excluded]) -> int:
    """Return the number of words in non-overlapping runs."""
    return sum(run.size for run in excluded)
