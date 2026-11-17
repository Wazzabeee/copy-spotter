"""Results of comparing documents."""

from __future__ import annotations

from dataclasses import dataclass

from copy_spotter.similarity import Match


@dataclass(frozen=True)
class PairResult:
    """Comparison of documents ``i`` and ``j`` (indexes into the document list).

    ``score`` is the symmetric similarity of the matching engine; ``coverage_i`` is the percentage of
    document ``i`` found in document ``j`` and ``coverage_j`` the percentage of ``j`` found in ``i``.
    """

    i: int
    j: int
    score: float
    blocks: list[Match]
    coverage_i: float
    coverage_j: float

    def scores(self, score_mode: str = "coverage") -> tuple[float, float]:
        """Return the score shown for (``i`` in ``j``, ``j`` in ``i``); both are ``score`` in ratio mode."""
        if score_mode == "ratio":
            return self.score, self.score
        return self.coverage_i, self.coverage_j

    @property
    def filename(self) -> str:
        return f"{self.i}_{self.j}.html"
