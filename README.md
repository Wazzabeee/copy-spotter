# Copy Spotter

[![PyPI - Version](https://img.shields.io/pypi/v/copy-spotter)](https://pypi.org/project/copy-spotter/)
[![Python versions](https://img.shields.io/pypi/pyversions/copy-spotter)](https://pypi.org/project/copy-spotter/)
[![CI](https://github.com/Wazzabeee/copy-spotter/actions/workflows/ci.yml/badge.svg)](https://github.com/Wazzabeee/copy-spotter/actions/workflows/ci.yml)
[![PyPI - License](https://img.shields.io/pypi/l/copy-spotter)](LICENSE)

![GIF demo](https://raw.githubusercontent.com/Wazzabeee/copy-spotter/main/data/img/example.gif)

## About

Copy Spotter compares every pair of documents (pdf, docx, odt, txt) found in a directory. It computes a similarity
score for each pair and writes an HTML report: a list of the most similar pairs, a similarity matrix, and a side by
side view of each pair where identical passages are highlighted with the same color.

Everything runs locally: your documents never leave your machine.

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
             [--report {single,pages}] [-r] [--no-open] [-V] in_dir
```

| Argument | Description |
| --- | --- |
| `in_dir` | Directory containing the documents to compare (pdf, docx, odt, txt). |
| `-o`, `--out-dir` | Directory for the HTML results. Created if missing. Default: `./results/<timestamp>`. |
| `-s`, `--block-size` | Minimum number of consecutive identical words to highlight. Default: 2. |
| `--score` | `coverage` (default): percentage of each document found in the other, so a short text fully copied into a long one scores 100% in that direction. `ratio`: the symmetric similarity ratio of the pair. |
| `--engine` | Matching algorithm: `shingle` (default) finds copied passages in any order, `difflib` is the legacy in-order matcher. |
| `--report` | `single` (default): one self-contained `_results.html` file. `pages`: `_results.html` plus one page per pair. |
| `-r`, `--recursive` | Also look for documents in subdirectories. |
| `--no-open` | Do not open the results in a web browser. |
| `-V`, `--version` | Show the version and exit. |

Empty files and PDFs without a text layer (scanned documents) are skipped with a warning.

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
