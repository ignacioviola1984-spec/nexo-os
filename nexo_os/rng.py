"""A tiny deterministic RNG wrapper. Used only by the synthetic generator and tests
so that a fixed seed yields a byte-for-byte reproducible dataset. Never used in the
deterministic core or agents — figures are computed, never sampled.
"""

from __future__ import annotations

import random
from collections.abc import Sequence


class DeterministicRng:
    def __init__(self, seed: int) -> None:
        self._r = random.Random(seed)

    def randint(self, lo: int, hi: int) -> int:
        return self._r.randint(lo, hi)

    def random(self) -> float:
        return self._r.random()

    def choice(self, seq: Sequence):
        return seq[self._r.randrange(len(seq))]

    def sample(self, seq: Sequence, k: int) -> list:
        return self._r.sample(list(seq), k)

    def shuffle(self, seq: list) -> None:
        self._r.shuffle(seq)

    def weighted(self, options: Sequence[tuple[str, float]]) -> str:
        """Pick a label from (label, weight) pairs."""
        total = sum(w for _, w in options)
        x = self._r.random() * total
        upto = 0.0
        for label, w in options:
            upto += w
            if x <= upto:
                return label
        return options[-1][0]
