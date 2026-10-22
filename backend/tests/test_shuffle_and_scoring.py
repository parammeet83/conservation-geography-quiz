"""Unit tests for the shuffle and percentage helpers (no database required)."""

import itertools
from collections import Counter
from decimal import Decimal

import pytest

from app.services.quiz import percent
from app.shuffle import SecureRandom, fisher_yates
from tests.conftest import SeededRandom


def test_shuffle_is_a_permutation_and_does_not_mutate_input():
    items = list(range(120))
    original = list(items)
    out = fisher_yates(items, SecureRandom())
    assert items == original
    assert sorted(out) == original
    assert len(out) == 120


def test_shuffle_is_reproducible_with_injected_rng():
    assert fisher_yates("ABCD", SeededRandom(7)) == fisher_yates("ABCD", SeededRandom(7))


def test_shuffle_reaches_every_permutation_of_four_options_roughly_uniformly():
    rng = SeededRandom(2026)
    counts = Counter(tuple(fisher_yates("abcd", rng)) for _ in range(24_000))
    assert set(counts) == set(itertools.permutations("abcd"))
    # 24 permutations x ~1000 each; a biased shuffle would skew far outside this band.
    assert min(counts.values()) > 850
    assert max(counts.values()) < 1150


def test_shuffle_handles_trivial_inputs():
    assert fisher_yates([], SecureRandom()) == []
    assert fisher_yates([1], SecureRandom()) == [1]


@pytest.mark.parametrize(
    ("correct", "total", "expected"),
    [
        (0, 10, "0.00"),
        (10, 10, "100.00"),
        (7, 10, "70.00"),
        (1, 120, "0.83"),
        (1, 3, "33.33"),
        (2, 3, "66.67"),
        (119, 120, "99.17"),
        (61, 120, "50.83"),
        (120, 120, "100.00"),
    ],
)
def test_percent_rounds_to_two_decimals(correct, total, expected):
    assert percent(correct, total) == Decimal(expected)
