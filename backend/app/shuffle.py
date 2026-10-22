"""Unbiased Fisher-Yates shuffling with an injectable random source."""

import secrets
from collections.abc import Sequence
from typing import Protocol


class RandomSource(Protocol):
    def randbelow(self, n: int) -> int: ...


class SecureRandom:
    """Default random source backed by the OS CSPRNG."""

    def randbelow(self, n: int) -> int:
        return secrets.randbelow(n)


def fisher_yates[T](items: Sequence[T], rng: RandomSource) -> list[T]:
    """Return a new shuffled list; the input sequence is never mutated."""
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = rng.randbelow(i + 1)
        out[i], out[j] = out[j], out[i]
    return out
