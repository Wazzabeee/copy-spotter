"""Progress events sent while documents are read and compared."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Stage = Literal["read", "compare"]


@dataclass(frozen=True)
class Progress:
    """``done`` of the ``total`` items of ``stage`` are finished.

    Each stage first sends an event with ``done == 0``, then one event per finished item, so the last event of a
    stage has ``done == total``. An exception raised by the callback stops the run and propagates to the caller.

    Attributes:
        stage: ``"read"`` (files read by :func:`load_directory`) or ``"compare"`` (pairs compared by
            :func:`compare_documents`).
        done: Items finished so far.
        total: Items in this stage.
    """

    stage: Stage
    done: int
    total: int


ProgressCallback = Callable[[Progress], None]


def emit(progress: ProgressCallback | None, stage: Stage, done: int, total: int) -> None:
    """Send a progress event if there is a callback."""
    if progress is not None:
        progress(Progress(stage, done, total))
