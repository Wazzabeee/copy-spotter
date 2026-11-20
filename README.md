# Copy Spotter

[![PyPI - Version](https://img.shields.io/pypi/v/copy-spotter)](https://pypi.org/project/copy-spotter/)
[![Python versions](https://img.shields.io/pypi/pyversions/copy-spotter)](https://pypi.org/project/copy-spotter/)
[![CI](https://github.com/Wazzabeee/copy-spotter/actions/workflows/ci.yml/badge.svg)](https://github.com/Wazzabeee/copy-spotter/actions/workflows/ci.yml)
[![PyPI - License](https://img.shields.io/pypi/l/copy-spotter)](LICENSE)

![GIF demo](https://raw.githubusercontent.com/Wazzabeee/copy-spotter/main/data/img/example.gif)

## About

Copy Spotter compares every pair of documents (pdf, docx, odt, txt, md, html, rtf, ipynb) found in a directory. It computes a similarity
score for each pair and writes an HTML report: a list of the most similar pairs, a similarity matrix, and a side by
side view of each pair where identical passages are highlighted with the same color.

Everything runs locally: your documents never leave your machine.

## Use it in your browser

No installation needed: open **[wazzabeee.github.io/copy-spotter](https://wazzabeee.github.io/copy-spotter/)**, drop
your documents or a folder, and read the report in the page. It runs the same code as the command line inside your
browser tab (with [Pyodide](https://pyodide.org)), so your files are never uploaded, and you can download the report
as HTML, JSON or CSV. The first visit downloads about 23 MB. It works in a recent browser, on a computer or a phone.
Large batches are faster with the command line. The source is in [`web/`](web/).

## Installation

```bash
pip install copy-spotter
```

or, to run it without installing it permanently:

```bash
uvx copy-spotter path/to/documents
```

Python 3.10 or newer is required.

## Usage

```bash
copy-spotter [-h] [-o OUT_DIR] [-s BLOCK_SIZE] [--score {coverage,ratio}] [--engine {shingle,difflib}]
             [--normalize accents] [--stopwords LANGS_OR_FILE] [--ignore-quotes] [--ignore-bibliography]
             [--exclude FILE_OR_DIR] [--ignore-common PCT] [--report {single,pages}] [--json PATH] [--csv PATH] [--thresholds LOW,MEDIUM,HIGH] [-r]
             [--no-open] [-V] in_dir
```

| Argument | Description |
| --- | --- |
| `in_dir` | Directory containing the documents to compare (pdf, docx, odt, txt, md, html, rtf, ipynb). |
| `-o`, `--out-dir` | Directory for the HTML results. Created if missing. Default: `./results/<timestamp>`. |
| `-s`, `--block-size` | Minimum number of consecutive identical words to highlight. Default: 2. |
| `--score` | `coverage` (default): percentage of each document found in the other, so a short text fully copied into a long one scores 100% in that direction. `ratio`: the symmetric similarity ratio of the pair. |
| `--engine` | Matching algorithm: `shingle` (default) finds copied passages in any order, `difflib` is the legacy in-order matcher. |
| `--normalize accents` | Ignore accents and ligatures when matching, so `élève` matches `eleve`. |
| `--stopwords` | Leave common words out of the matching: built-in lists for `en`, `fr`, `es`, `de`, `it`, `pt` (comma separated, for instance `en,fr`), or the path of a text file of words. |
| `--ignore-quotes` | Leave passages between quotation marks out of the matching. They are shown in grey in the report. |
| `--ignore-bibliography` | Leave the bibliography (the end of the document after a heading such as References, Bibliography or Works cited) out of the matching. |
| `--exclude` | Text everyone was given (assignment prompt, template, starter code): passages of four words or more found in it are left out of the matching. A file or a directory; repeatable. |
| `--ignore-common PCT` | Leave out of the matching the passages found in more than PCT% of the documents, and in at least three. |
| `--report` | `single` (default): one self-contained `_results.html` file. `pages`: `_results.html` plus one page per pair. |
| `--json PATH` | Also write the pairs, scores and matching blocks as JSON. |
| `--csv PATH` | Also write one CSV row per pair. |
| `--thresholds` | Score percentages above which scores are shown in yellow, orange and red, applied to the score chosen by `--score`: three increasing numbers between 0 and 100. Default: `5,10,15`. |
| `-r`, `--recursive` | Also look for documents in subdirectories. |
| `--no-open` | Do not open the results in a web browser. |
| `-V`, `--version` | Show the version and exit. |

Empty files and PDFs without a text layer (scanned documents) are skipped with a warning.

### Matching options

By default words must be identical, apart from case and punctuation. Two options loosen this, both off by default:

- `--normalize accents` folds accents and compatibility characters before matching: `élève` matches `eleve`, and the
  `ﬁ` ligature found in some PDFs matches `fi`.
- `--stopwords en` leaves common words (articles, pronouns, prepositions...) out of the matching, so a passage where
  only `the` became `a` is still one copied block. Stopwords are not counted in the scores either: coverage is the
  share of the other words. Built-in lists: `en`, `fr`, `es`, `de`, `it`, `pt`; combine them with `en,fr`, or give a
  text file with your own words.

The report still shows the original text: a block is highlighted from its first to its last word, stopwords
included. The options in use are listed under the title of the report and in the `options` field of the JSON export.
Stemming (matching `copied` with `copying`) is not supported.

### Quotations and bibliographies

Quoting a source is not copying it. Two options leave such passages out of the matching, both off by default:

- `--ignore-quotes`: text between quotation marks: `"..."`, `“...”`, `„...“`, `«...»`, `»...«` and `「...」`. Single
  quotes are not used because they are also apostrophes. A quotation must close in the paragraph where it opens, so a
  stray quotation mark cannot hide the rest of a document.
- `--ignore-bibliography`: the text from the last heading such as `References`, `Bibliography`, `Works cited`,
  `Bibliographie`, `Referencias` or `Literaturverzeichnis` (alone on its line, optionally numbered, past the first 30%
  of the document) to the end. In PDF text where the heading was joined to the first entry, an entry starting with
  `[1]`, `1.` or `Surname,` is recognized too.

Excluded passages stay in the report, in grey, but their words never match, so copied passages stop where a quotation
starts. They still count in the length of the document: excluding passages can only lower a score. The JSON export
lists them per document (`excluded_words`, and `excluded` runs with `start`, `size` and `reason`).

### Templates and shared text

When students start from the same prompt or template, the text they all copied from it is not plagiarism:

- `--exclude prompt.docx` (repeatable, a file or a directory of documents) leaves out of the matching every passage
  of at least four words that is also in a template. Shorter shared phrases ("one of the") are kept, so they do not cut
  real copied passages into pieces. Templates are read like the other documents (all formats) and are not compared
  with each other; a template inside the input folder is not compared as a submission.
- `--ignore-common 50` finds such text automatically: passages found in more than 50% of the documents, and in at
  least three, are left out. The documents are compared twice, so this doubles the run time.

As with quotations, excluded passages are shown in grey in the report, still count in the length of each document,
and are listed in the JSON export with the reason `template` or `common`.

### Supported formats

| Format | Extensions | What is compared |
| --- | --- | --- |
| PDF | `.pdf` | The text layer. Lines broken in the middle of a paragraph are joined. Scanned PDFs need OCR first. |
| Word, OpenDocument | `.docx`, `.odt` | Paragraphs and headings. |
| Plain text | `.txt` | The whole file (UTF-8, cp1252 or latin-1). |
| Markdown | `.md` | The text as written, without link targets, image paths, inline HTML and `_` emphasis marks. |
| HTML | `.html`, `.htm` | The visible text: no scripts, styles or page title. HTML files next to a `_results.html` file are a copy-spotter report and are skipped. |
| Rich Text | `.rtf` | The document text, without fonts, metadata, pictures or field codes. |
| Jupyter notebook | `.ipynb` | Markdown and code cells; outputs are left out. |

Every format is read with the Python standard library or the two parsers copy-spotter already depends on, so
`Document.from_bytes` works the same everywhere, including in the browser with Pyodide.

### Examples

```bash
# Compare the example documents with default settings
copy-spotter data/pdf/plagiarism

# Only highlight runs of 5 identical words or more, and choose the output directory
copy-spotter data/pdf/plagiarism -s 5 -o results/output
```

By default the report is a single file, `_results.html`, that works offline: it lists the pairs sorted by score, the
similarity matrix, filters on minimum score and document name, and shows any pair side by side with its original text.
With `--report pages` the results directory holds `_results.html` plus one HTML page per pair; zip it to share it.

### Exports

`--json` and `--csv` write the results in a form other tools can read, with pairs sorted by their highest score in
the `--score` mode, highest first. Field names are stable; new fields may be added later.

- JSON: `version`, `copy_spotter_version`, `engine`, `score_mode`, `block_size`, `thresholds`, `options` (only when
  matching options are on, for instance `{"normalize": ["accents"], "stopwords": 174}`), `documents`
  (`index`, `name`, `word_count`) and `pairs` (`document_1`, `document_2`, `index_1`, `index_2`, `coverage_1`,
  `coverage_2`, `ratio`, `matched_words`, and `blocks` with `start_1`, `start_2`, `size`). `coverage_1` is the % of
  document 1 found in document 2. Block positions count extracted words from 0.
- CSV columns: `document_1`, `document_2`, `coverage_1`, `coverage_2`, `ratio`, `matched_words`, `block_count`.

```bash
copy-spotter data/pdf/plagiarism --json pairs.json --csv pairs.csv --no-open
```

## Python API

Everything the command does is available from Python, without touching the filesystem if you do not want to:
documents can be read from bytes and every report is available as a string.

```python
from copy_spotter import Document, compare_documents, load_directory

# Read every supported file of a directory; documents are named by their path relative to it.
documents = load_directory("data/pdf/plagiarism")

# Documents can also come from memory: the bytes of any supported file, or plain text.
documents.append(Document.from_text("Artificial intelligence is transforming healthcare.", "note.txt"))

results = compare_documents(documents, block_size=3)

# Pairs sorted by their higher score, highest first. coverage_i is the % of document i found in document j.
for pair in results.ranked()[:3]:
    a, b = results.documents[pair.i], results.documents[pair.j]
    print(f"{a.name} / {b.name}: {pair.coverage_i:.1f}% / {pair.coverage_j:.1f}%, {len(pair.blocks)} blocks")

# Render as strings, or write the HTML report like the command does.
html = results.to_html(score="ratio", thresholds=(10, 20, 30))
data = results.to_dict()
report = results.save("results/api", report="pages")
```

- `Document.from_path(path)`, `Document.from_bytes(data, name, format=None)` and `Document.from_text(text, name)`
  build a document; a `Document` holds its `name`, display `text`, lowercase `words` and the `spans` of the words.
- `compare_documents(documents, block_size=2, engine="shingle", normalize=(), stopwords=(), ignore_quotes=False,
  ignore_bibliography=False, templates=(), ignore_common=None, progress=None)` returns
  `Results`: the documents and one `Pair` per pair (`i`, `j`, `coverage_i`, `coverage_j`, `ratio`, matching
  `blocks`). `normalize=["accents"]` and `stopwords=stopword_list("en", "fr")` are the `--normalize` and
  `--stopwords` options; `ignore_quotes=True`, `ignore_bibliography=True`, `templates=[Document, ...]` and
  `ignore_common=50` the exclusion options. `Results.options`
  records the options in use and `Results.excluded` the excluded word runs of each document.
- `Results.ranked(score)`, `pair(a, b)`, `to_dict`, `to_json`, `to_csv`, `to_html`, `to_html_pages` and `save` take
  the score mode and thresholds when rendering, so one comparison can be shown several ways.
- `load_directory(directory, recursive=False, on_skip=None, progress=None)` reports skipped files to `on_skip`;
  `progress` receives `Progress(stage, done, total)` events. Errors derive from `CopySpotterError`:
  `UnsupportedFormatError` and `DocumentReadError` (from `Document.from_bytes` and `from_path`).

## How it works

1. Text is extracted from each document and split into lowercase words.
2. Each pair of documents is compared with the shingle engine: the word n-grams of one document are indexed (n is
   `--block-size`, at least 2), every n-gram shared with the other document is extended into the longest run of
   identical words, and runs are kept longest first so that no word is matched twice. Copied passages are found even
   when they were moved around. Runs shorter than `--block-size` words are ignored.
3. By default each pair gets two scores: the percentage of the words of A that are inside a matching run (A found in
   B), and the same for B. In the matrix, the cell at row A, column B is the percentage of A found in B. With
   `--score ratio`, the score is the symmetric ratio of the pair instead, `2 * matched words / total words * 100`.
   With the shingle engine only runs of at least `--block-size` words count, so a larger block size gives a lower
   ratio.
4. The matching runs are highlighted in the side by side view.

`--engine difflib` keeps the previous matching, based on Python's `difflib.SequenceMatcher`: it follows a single
in-order alignment (a passage moved elsewhere is missed), ignores words that are very frequent in texts over 200 words,
and its ratio also counts isolated shared words.

### Known limitations

- Only exact word matches are detected: paraphrased or translated passages are not.
- With `--score ratio`, the score is diluted when documents have very different lengths (a short text fully copied
  into a long one gets a low score). The default coverage score does not have this problem.
- The shingle engine ignores matches shorter than two words, so documents of a single word never match.
- Scanned PDFs need OCR before they can be compared.
- The side by side view shows the extracted plain text (case, punctuation and paragraphs), not the original layout:
  fonts, tables and images are not rendered, and some PDFs may still show odd line breaks.

## Development

```bash
git clone https://github.com/Wazzabeee/copy-spotter
cd copy-spotter

# Install the package and the dev tools in .venv (requires uv: https://docs.astral.sh/uv/)
uv sync

# Install the git hooks
uv run pre-commit install

# Run the tests, the linter and the type checker
uv run pytest
uv run ruff check .
uv run mypy

# Run the CLI from the source tree
uv run copy-spotter data/pdf/plagiarism
```

`tests/test_golden.py` freezes the CLI outputs (HTML reports, JSON and CSV exports) for the documents in
`tests/golden/inputs`. When a change to the outputs is intended, regenerate the goldens and review the diff
before committing:

```bash
COPY_SPOTTER_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py
```

### Releasing

Push a version tag; the release workflow runs the tests, publishes to PyPI with trusted publishing and creates the
GitHub release.

```bash
git tag v0.2.0
git push origin v0.2.0
```

## Contributing

Bug reports and pull requests are welcome. If a document is not processed correctly, please
[open an issue](https://github.com/Wazzabeee/copy-spotter/issues) and attach it if you can.
