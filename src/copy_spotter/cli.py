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

from copy_spotter._compare import PairResult
from copy_spotter._documents import Document, find_documents
from copy_spotter._errors import CopySpotterError
from copy_spotter._export import write_csv, write_json
from copy_spotter._options import DEFAULT_THRESHOLDS, REPORT_LAYOUTS, SCORE_MODES, check_block_size, check_thresholds
from copy_spotter._report import write_report
from copy_spotter._single_page import write_single_report
from copy_spotter._version import __version__
from copy_spotter.extract import SUPPORTED_EXTENSIONS
from copy_spotter.similarity import DEFAULT_ENGINE, ENGINES, compare, coverage


def parse_thresholds(text: str) -> tuple[float, float, float]:
    """Parse ``"5,10,15"`` into three increasing percentages between 0 and 100."""
    try:
        values = tuple(float(part) for part in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected three numbers such as 5,10,15, got {text!r}") from None
    if len(values) != 3:
        raise argparse.ArgumentTypeError(f"expected three numbers such as 5,10,15, got {len(values)}")
    try:
        return check_thresholds(values)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"thresholds must be increasing percentages between 0 and 100, got {text!r}"
        ) from None


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
    parser.add_argument(
        "--report",
        choices=REPORT_LAYOUTS,
        default="single",
        help="single: one self-contained HTML file (default); pages: a summary page plus one page per pair",
    )
    parser.add_argument(
        "--json", dest="json_path", type=Path, metavar="PATH", help="also write the pairs and matching blocks as JSON"
    )
    parser.add_argument("--csv", dest="csv_path", type=Path, metavar="PATH", help="also write one CSV row per pair")
    parser.add_argument(
        "--thresholds",
        type=parse_thresholds,
        default=DEFAULT_THRESHOLDS,
        metavar="LOW,MEDIUM,HIGH",
        help="score percentages above which scores are shown in yellow, orange and red (default: 5,10,15)",
    )
    parser.add_argument("-r", "--recursive", action="store_true", help="also look for documents in subdirectories")
    parser.add_argument("--no-open", action="store_true", help="do not open the results in a web browser")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    try:
        check_block_size(args.block_size)
    except ValueError:
        parser.error("--block-size must be at least 1")
    return args


def run(args: argparse.Namespace) -> Path:
    """Compare the documents and write the report. Return the path of the summary page."""
    in_dir: Path = args.in_dir.resolve()
    if not in_dir.is_dir():
        raise CopySpotterError(f"Input directory not found: {args.in_dir}")

    out_dir: Path = (args.out_dir or Path("results") / datetime.now().strftime("%Y%m%d_%H%M%S")).resolve()

    paths = find_documents(in_dir, recursive=args.recursive, exclude=out_dir)
    names, texts, documents = [], [], []
    for path in tqdm(paths, desc="Reading files", disable=None):
        name = path.relative_to(in_dir).as_posix()
        try:
            document = Document.from_path(path, name=name)
        except Exception as exc:  # a corrupt file should not stop the whole run
            print(f"Warning: skipping {name}: could not read it ({exc.__cause__ or exc})", file=sys.stderr)
            continue
        if not document.words:
            print(f"Warning: skipping {name}: no text found (empty file or scanned PDF?)", file=sys.stderr)
            continue
        names.append(name)
        texts.append(list(document.words))
        documents.append(document)

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
    if args.json_path is not None:
        json_path = write_json(
            args.json_path.resolve(),
            names,
            documents,
            pairs,
            block_size=args.block_size,
            engine=args.engine,
            score_mode=args.score,
            thresholds=args.thresholds,
        )
        print(f"JSON saved at: {json_path}")
    if args.csv_path is not None:
        print(f"CSV saved at: {write_csv(args.csv_path.resolve(), names, pairs, score_mode=args.score)}")
    if args.report == "pages":
        return write_report(out_dir, names, documents, pairs, meta, score_mode=args.score, thresholds=args.thresholds)
    return write_single_report(
        out_dir, names, documents, pairs, meta, score_mode=args.score, thresholds=args.thresholds
    )


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
