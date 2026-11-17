# Changelog

## Unreleased

### Features
- Scores take document length into account: each pair now has two directional coverage scores, the percentage of
  each document found in the other. A short text fully copied into a long document scores 100% in that direction.
- The similarity matrix is no longer symmetric: the cell at row A, column B is the percentage of A found in B.
- The pairs list shows both directions and is sorted by the higher one; comparison pages show both directions.
- New `--score {coverage,ratio}` option. `coverage` is the default; `ratio` shows the symmetric similarity ratio of
  the pair everywhere, as before.
- New default matching engine, `shingle`: indexes word n-grams and finds copied passages in any order, including
  passages that were moved around, which difflib missed. It does not skip frequent words, and on 20 generated
  documents of 5000 words it runs about twice as fast as difflib.
- New option `--engine {shingle,difflib}`. `--engine difflib` gives the same results as before.
- Comparison pages show each document's original text, with its case, punctuation and paragraph breaks, and the
  matching passages highlighted in place. Lines that a PDF breaks in the middle of a paragraph are joined. Matching
  and scores are unchanged.
- New `extract_document()` returns the display text, the words and the position of each word in the text.

### Changes
- With the default `shingle` engine, coverage and ratio scores only count runs of at least `--block-size` words (at
  least 2), and passages moved around count too, so scores differ from previous versions. The ratio decreases when
  the block size grows. Use `--engine difflib` for the previous results.

## 0.2.0 (unreleased)

### Breaking changes
- The Python package is now `copy_spotter` (it was `scripts`). The `copy-spotter` command is unchanged; use
  `python -m copy_spotter` instead of `python -m scripts.main`.
- Each pair of documents is compared once: the report contains one page per pair instead of two, named `<i>_<j>.html`.

### Fixes
- Results are written to `./results/<timestamp>` in the current directory, not in its parent.
- `-o` creates the output directory when it does not exist instead of silently ignoring it.
- Links in the results table work when the output path contains `_results`, and when a file name is a number.
- Links are relative, so the results folder can be moved or shared.
- Text files that are not UTF-8 (for example Windows cp1252) are read instead of crashing.
- Empty files, scanned PDFs and unreadable files are skipped with a clear warning.
- Highlighting respects word boundaries ("le chat" is no longer highlighted inside "le chaton").
- DOCX and ODT paragraphs are no longer glued together, and ODT headings are read.
- Uppercase extensions (`.PDF`, `.TXT`) are supported.

### Features
- The results page lists pairs sorted by similarity, above the matrix.
- Each comparison page shows the score and links back to the results.
- Deterministic, readable highlight colors.
- New options: `--recursive`, `--no-open`, `--version`. `--out-dir` and `--block-size` are accepted next to the old
  `--out_dir` and `--block_size` spellings.

### Chore
- Packaging moved to `pyproject.toml` (hatchling, version from git tags), `src/` layout, managed with uv.
- Removed the NLTK, BeautifulSoup and tabulate dependencies, and unused code.
- Tests for every module, CI on Python 3.10 to 3.14 (Linux, macOS, Windows), ruff and strict mypy.
- PyPI releases on version tags with trusted publishing.

## 0.0.1

authors: Wazzabeee

### Chore
- Add pre commit hooks
- Update requirements for security reasons

### Fixes
- Fix README example
- Fix saving path with slashes
