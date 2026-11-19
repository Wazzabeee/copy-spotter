# Changelog

## Unreleased

### Features
- New input formats: Markdown (`.md`), HTML (`.html`, `.htm`, visible text only), Rich Text (`.rtf`) and Jupyter
  notebooks (`.ipynb`, Markdown and code cells). They are read with the standard library only and work with
  `Document.from_bytes`. HTML files next to a `_results.html` file (an earlier copy-spotter report) are skipped.
- `--normalize accents` folds accents and ligatures before matching, and `--stopwords LANGS_OR_FILE` leaves common
  words out of the matching (built-in lists for en, fr, es, de, it, pt, or a file of words). Both are off by default;
  the report still shows the original text. Python API: `compare_documents(normalize=..., stopwords=...)` and
  `stopword_list()`. The JSON export gains an `options` field when matching options are on.
- `--ignore-quotes` and `--ignore-bibliography` leave quotations (straight and curly quotes, guillemets, German and
  CJK quotation marks) and the trailing bibliography out of the matching. Excluded passages are shown in grey in the
  reports and listed in the JSON export; they still count in the document length. Python API:
  `compare_documents(ignore_quotes=..., ignore_bibliography=...)` and `Results.excluded`.
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
- The report is now a single self-contained `_results.html` file (no external resources, works offline) with the
  sorted pairs, the matrix, filters on minimum score and document name, and a side-by-side view of any pair with its
  original text. `--report pages` keeps the multi-page output: a summary page plus one page per pair.
- `--json PATH` and `--csv PATH` export the pairs sorted by score: names, both coverages, the ratio and the matching
  blocks in JSON, with the engine and score mode of the run; one row per pair in CSV.
- `--thresholds LOW,MEDIUM,HIGH` sets the percentages at which the shown score (coverage or ratio) turns yellow,
  orange and red (default `5,10,15`, previously hardcoded).
- Python API: `load_directory()`, `Document.from_path()`, `from_bytes()` and `from_text()` read documents (from
  memory too), `compare_documents()` compares them and returns `Results`, which renders the HTML report, JSON and
  CSV as strings or saves them, with the score mode and thresholds chosen at render time. Progress callbacks,
  typed errors (`CopySpotterError`) and type hints (`py.typed`) included. See the README.
- Importing copy-spotter no longer loads the PDF and ODT parsers; they are imported when such a file is read.

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
