"""Command line entry point: compare every pair of documents in a directory."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from tqdm import tqdm

from copy_spotter._compare import compare_documents
from copy_spotter._documents import Skipped, load_directory
from copy_spotter._errors import CopySpotterError
from copy_spotter._options import DEFAULT_THRESHOLDS, REPORT_LAYOUTS, SCORE_MODES, check_block_size, check_thresholds
from copy_spotter._progress import Progress
from copy_spotter._version import __version__
from copy_spotter.extract import SUPPORTED_EXTENSIONS
from copy_spotter.similarity import DEFAULT_ENGINE, ENGINES

_STAGE_DESCRIPTIONS = {"read": "Reading files", "compare": "Comparing files"}


class TqdmProgress:
    """Show progress events as one tqdm bar per stage (hidden when stderr is not a terminal)."""

    def __init__(self) -> None:
        self._bars: dict[str, tqdm[NoReturn]] = {}

    def __call__(self, event: Progress) -> None:
        bar = self._bars.get(event.stage)
        if bar is None:
            bar = self._bars[event.stage] = tqdm(total=event.total, desc=_STAGE_DESCRIPTIONS[event.stage], disable=None)
        bar.update(event.done - bar.n)
        if event.done == event.total:
            bar.close()


def _warn_skipped(skipped: Skipped) -> None:
    if skipped.reason == "empty":
        print(f"Warning: skipping {skipped.name}: no text found (empty file or scanned PDF?)", file=sys.stderr)
    else:
        error = skipped.error.__cause__ or skipped.error if skipped.error is not None else None
        print(f"Warning: skipping {skipped.name}: could not read it ({error})", file=sys.stderr)


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
        description="Compare every pair of documents (pdf, docx, odt, txt, md, html, rtf, ipynb) in a directory "
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

    progress = TqdmProgress()
    documents = load_directory(
        in_dir, recursive=args.recursive, exclude=out_dir, on_skip=_warn_skipped, progress=progress
    )
    if len(documents) < 2:
        raise CopySpotterError(
            f"Need at least two readable documents in {in_dir}, found {len(documents)}. "
            f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    results = compare_documents(documents, block_size=args.block_size, engine=args.engine, progress=progress)

    meta = (
        f"{len(documents)} documents from {in_dir.name}/, minimum block size {args.block_size}, "
        f"{args.engine} engine, {args.score} score, copy-spotter {__version__}"
    )
    if args.json_path is not None:
        json_path: Path = args.json_path.resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(results.to_json(score=args.score, thresholds=args.thresholds), encoding="utf-8")
        print(f"JSON saved at: {json_path}")
    if args.csv_path is not None:
        csv_path: Path = args.csv_path.resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(results.to_csv(score=args.score), encoding="utf-8", newline="")
        print(f"CSV saved at: {csv_path}")
    return results.save(out_dir, report=args.report, score=args.score, thresholds=args.thresholds, meta=meta)


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
