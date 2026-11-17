"""Command line entry point: compare every pair of documents in a directory."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from collections.abc import Sequence
from datetime import datetime
from itertools import combinations
from pathlib import Path

from tqdm import tqdm

from copy_spotter import __version__
from copy_spotter.extract import SUPPORTED_EXTENSIONS, extract_words, is_supported
from copy_spotter.report import SCORE_MODES, PairResult, write_report
from copy_spotter.similarity import DEFAULT_ENGINE, ENGINES, compare, coverage


class CopySpotterError(Exception):
    """Error shown to the user without a traceback."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="copy-spotter",
        description="Compare every pair of documents (pdf, docx, odt, txt) in a directory "
        "and highlight similar passages.",
    )
    parser.add_argument("in_dir", type=Path, help="directory containing the documents to compare")
    parser.add_argument(
        "-o",
        "--out-dir",
        "--out_dir",
        dest="out_dir",
        type=Path,
        help="directory for the HTML results (created if missing; default: ./results/<timestamp>)",
    )
    parser.add_argument(
        "-s",
        "--block-size",
        "--block_size",
        dest="block_size",
        type=int,
        default=2,
        help="minimum number of consecutive identical words to highlight (default: 2)",
    )
    parser.add_argument(
        "--score",
        choices=SCORE_MODES,
        default="coverage",
        help="coverage: %% of each document found in the other (asymmetric); "
        "ratio: symmetric similarity ratio of the pair (default: coverage)",
    )
    parser.add_argument(
        "--engine",
        choices=ENGINES,
        default=DEFAULT_ENGINE,
        help="matching algorithm: shingle finds copied passages in any order, difflib is the legacy in-order "
        f"matcher (default: {DEFAULT_ENGINE})",
    )
    parser.add_argument("-r", "--recursive", action="store_true", help="also look for documents in subdirectories")
    parser.add_argument("--no-open", action="store_true", help="do not open the results in a web browser")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.block_size < 1:
        parser.error("--block-size must be at least 1")
    return args


def find_documents(in_dir: Path, recursive: bool = False, exclude: Path | None = None) -> list[Path]:
    """Return the supported documents in ``in_dir``, sorted by path."""
    candidates = in_dir.rglob("*") if recursive else in_dir.iterdir()
    documents = []
    for path in candidates:
        if not path.is_file() or not is_supported(path) or path.name.startswith("."):
            continue
        if exclude is not None and path.resolve().is_relative_to(exclude):
            continue
        documents.append(path)
    return sorted(documents)


def run(args: argparse.Namespace) -> Path:
    """Compare the documents and write the report. Return the path of the summary page."""
    in_dir: Path = args.in_dir.resolve()
    if not in_dir.is_dir():
        raise CopySpotterError(f"Input directory not found: {args.in_dir}")

    out_dir: Path = (args.out_dir or Path("results") / datetime.now().strftime("%Y%m%d_%H%M%S")).resolve()

    paths = find_documents(in_dir, args.recursive, exclude=out_dir)
    names, texts = [], []
    for path in tqdm(paths, desc="Reading files", disable=None):
        name = path.relative_to(in_dir).as_posix()
        try:
            words = extract_words(path)
        except Exception as exc:  # a corrupt file should not stop the whole run
            print(f"Warning: skipping {name}: could not read it ({exc})", file=sys.stderr)
            continue
        if not words:
            print(f"Warning: skipping {name}: no text found (empty file or scanned PDF?)", file=sys.stderr)
            continue
        names.append(name)
        texts.append(words)

    if len(texts) < 2:
        raise CopySpotterError(
            f"Need at least two readable documents in {in_dir}, found {len(texts)}. "
            f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    pairs = []
    for i, j in tqdm(list(combinations(range(len(texts)), 2)), desc="Comparing files", disable=None):
        score, blocks = compare(texts[i], texts[j], args.block_size, args.engine)
        coverage_i, coverage_j = coverage(blocks, len(texts[i]), len(texts[j]))
        pairs.append(PairResult(i, j, score, blocks, coverage_i, coverage_j))

    meta = (
        f"{len(names)} documents from {in_dir.name}/, minimum block size {args.block_size}, "
        f"{args.engine} engine, {args.score} score, copy-spotter {__version__}"
    )
    return write_report(out_dir, names, texts, pairs, meta, score_mode=args.score)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        results = run(args)
    except CopySpotterError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Results saved at: {results}")
    if not args.no_open:
        webbrowser.open(results.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
