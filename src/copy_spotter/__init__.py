"""copy-spotter: find similar passages between documents and highlight them side by side."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("copy-spotter")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
