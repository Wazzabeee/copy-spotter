"""copy-spotter: find similar passages between documents and highlight them side by side.

Read documents, compare every pair, then render or save the results::

    from copy_spotter import compare_documents, load_directory

    documents = load_directory("essays")
    results = compare_documents(documents, block_size=3)
    for pair in results.ranked():
        print(results.documents[pair.i].name, results.documents[pair.j].name, pair.coverage_i, pair.coverage_j)
    results.save("report")

Documents can also be built from memory with :meth:`Document.from_bytes` or :meth:`Document.from_text`.
Importing this package is cheap: the PDF and ODT parsers are only imported when such a file is read.
"""

from copy_spotter._compare import Pair, compare_documents
from copy_spotter._documents import Document, Skipped, find_documents, load_directory
from copy_spotter._errors import CopySpotterError, DocumentReadError, UnsupportedFormatError
from copy_spotter._normalize import NORMALIZATIONS, STOPWORD_LANGUAGES, Normalization, stopword_list
from copy_spotter._options import DEFAULT_THRESHOLDS, ReportLayout, ScoreMode
from copy_spotter._progress import Progress
from copy_spotter._results import Results
from copy_spotter._version import __version__
from copy_spotter.extract import SUPPORTED_FORMATS
from copy_spotter.similarity import ENGINES, Engine, Match

__all__ = [
    "DEFAULT_THRESHOLDS",
    "ENGINES",
    "NORMALIZATIONS",
    "STOPWORD_LANGUAGES",
    "SUPPORTED_FORMATS",
    "CopySpotterError",
    "Document",
    "DocumentReadError",
    "Engine",
    "Match",
    "Normalization",
    "Pair",
    "Progress",
    "ReportLayout",
    "Results",
    "ScoreMode",
    "Skipped",
    "UnsupportedFormatError",
    "__version__",
    "compare_documents",
    "find_documents",
    "load_directory",
    "stopword_list",
]
