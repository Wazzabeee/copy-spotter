"""Exceptions raised by copy-spotter."""

from __future__ import annotations


class CopySpotterError(Exception):
    """Base class of the errors raised by copy-spotter."""


class UnsupportedFormatError(CopySpotterError, ValueError):
    """The format of a file is not one copy-spotter can read (see ``SUPPORTED_FORMATS``)."""


class DocumentReadError(CopySpotterError):
    """A file in a supported format could not be read (corrupt, encrypted...); the original error is the cause."""
