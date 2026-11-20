"""Command line entry point: compare every pair of documents in a directory."""

from __future__ import annotations

import argparse
import dataclasses
import sys
import webbrowser
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from tqdm import tqdm

from copy_spotter._compare import compare_documents
from copy_spotter._documents import Document, Skipped, load_directory
from copy_spotter._errors import CopySpotterError
from copy_spotter._normalize import NORMALIZATIONS, STOPWORD_LANGUAGES, stopword_list
from copy_spotter._options import DEFAULT_THRESHOLDS, REPORT_LAYOUTS, SCORE_MODES, check_block_size, check_thresholds
from copy_spotter._progress import Progress
from copy_spotter._results import describe_options
from copy_spotter._version import __version__
from copy_spotter.extract import SUPPORTED_EXTENSIONS, read_text, tokenize
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


def parse_stopwords(text: str) -> frozenset[str]:
    """Parse ``--stopwords``: language codes such as ``en,fr``, or the path of a file of words."""
    path = Path(text)
    if path.is_file():
        try:
            return frozenset(tokenize(read_text(path.read_bytes(), "txt")))
        except OSError as exc:
            raise argparse.ArgumentTypeError(f"cannot read {text}: {exc}") from None
    try:
        return stopword_list(*text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected languages among {','.join(STOPWORD_LANGUAGES)} or a file of words, got {text!r}"
        ) from None


def parse_percentage(text: str) -> float:
    """Parse ``--ignore-common``: a percentage above 0 and at most 100."""
    try:
        value = float(text.rstrip("%"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a percentage such as 50, got {text!r}") from None
    if not 0 < value <= 100:
        raise argparse.ArgumentTypeError(f"expected a percentage above 0 and at most 100, got {text!r}")
    return value


def load_paths(paths: Sequence[Path], on_skip: Callable[[Skipped], None], *, prefix: bool = False) -> list[Document]:
    """Read the documents given as files or directories (the supported files directly inside each directory).

    With ``prefix``, documents of a directory are named ``<directory name>/<file name>``.
    """
    documents: list[Document] = []
    for path in paths:
        if path.is_dir():
            found = load_directory(path, on_skip=on_skip)
            if prefix:
                found = [dataclasses.replace(d, name=f"{path.resolve().name}/{d.name}") for d in found]
            documents += found
        elif path.is_file():
            try:
                documents.append(Document.from_path(path))
            except (OSError, CopySpotterError) as exc:
                raise CopySpotterError(f"Could not read {path}: {exc.__cause__ or exc}") from exc
        else:
            raise CopySpotterError(f"Not found: {path}")
    return documents


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
        default=4,
        help="minimum number of consecutive identical words to highlight (default: 4)",
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
        "--normalize",
        action="append",
        choices=NORMALIZATIONS,
        default=[],
        help="accents: ignore accents and ligatures when matching, so 'élève' matches 'eleve' (repeatable)",
    )
    parser.add_argument(
        "--stopwords",
        type=parse_stopwords,
        metavar="LANGS_OR_FILE",
        help=f"leave common words out of the matching: languages among {','.join(STOPWORD_LANGUAGES)} "
        "(comma separated) or a text file of words",
    )
    parser.add_argument(
        "--ignore-quotes",
        action="store_true",
        help="leave passages between quotation marks out of the matching (shown in grey in the report)",
    )
    parser.add_argument(
        "--ignore-bibliography",
        action="store_true",
        help="leave the bibliography out of the matching: the text after the last heading such as References, "
        "Bibliography or Works cited",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        type=Path,
        default=[],
        metavar="FILE_OR_DIR",
        help="text everyone was given, such as the assignment prompt or a template: passages of four words or more "
        "found in it are left out of the matching (repeatable; a directory means every document in it)",
    )
    parser.add_argument(
        "--ignore-common",
        type=parse_percentage,
        metavar="PCT",
        help="leave out of the matching the passages found in more than PCT%% of the documents (and in at least 3)",
    )
    parser.add_argument(
        "--reference",
        action="append",
        type=Path,
        default=[],
        metavar="FILE_OR_DIR",
        help="reference sources (articles, past essays) to compare every document with; references are not "
        "compared with each other (repeatable; a directory means every document in it)",
    )
    parser.add_argument(
        "--reference-only",
        action="store_true",
        help="with --reference, compare each document with the references only, not with the other documents",
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
    if args.reference_only and not args.reference:
        raise CopySpotterError("--reference-only needs at least one --reference")
    if args.reference_only and args.ignore_common is not None:
        raise CopySpotterError(
            "--ignore-common counts the documents sharing a passage: it cannot be used with --reference-only"
        )
    templates = load_paths(args.exclude, _warn_skipped)
    references = load_paths(args.reference, _warn_skipped, prefix=True)
    documents = load_directory(
        in_dir,
        recursive=args.recursive,
        exclude=[out_dir, *args.exclude, *args.reference],
        on_skip=_warn_skipped,
        progress=progress,
    )
    needed = 1 if references else 2
    if len(documents) < needed:
        raise CopySpotterError(
            f"Need at least {'one readable document' if references else 'two readable documents'} in {in_dir}, "
            f"found {len(documents)}. Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    if args.reference and not references:
        raise CopySpotterError("No readable reference document found")
    clashes = sorted({d.name for d in documents} & {r.name for r in references})
    clashes += sorted(name for name, count in Counter(r.name for r in references).items() if count > 1)
    if clashes:
        raise CopySpotterError(f"Documents and references must have different names, found: {', '.join(clashes)}")
    results = compare_documents(
        documents,
        block_size=args.block_size,
        engine=args.engine,
        normalize=args.normalize,
        stopwords=args.stopwords or (),
        ignore_quotes=args.ignore_quotes,
        ignore_bibliography=args.ignore_bibliography,
        templates=templates,
        ignore_common=args.ignore_common,
        references=references,
        compare_submissions=not args.reference_only,
        progress=progress,
    )

    meta = (
        f"{len(documents)} documents from {in_dir.name}/, minimum block size {args.block_size}, "
        f"{args.engine} engine{describe_options(results.options)}, {args.score} score, copy-spotter {__version__}"
    )
    if args.json_path is not None:
        json_path: Path = args.json_path.resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        results.write_json(json_path, score=args.score, thresholds=args.thresholds)
        print(f"JSON saved at: {json_path}")
    if args.csv_path is not None:
        csv_path: Path = args.csv_path.resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        results.write_csv(csv_path, score=args.score)
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
