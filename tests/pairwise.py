"""All-pairs (pairwise) combination generator for the stack matrix.

Rendering and compiling *every* valid combination explodes as the catalogue
grows (axes multiply). Pairwise coverage instead picks a small set of valid
combinations such that **every satisfiable pair of option-values across any two
axes appears together in at least one combination** — which also guarantees
every individual option is exercised. This catches option-interaction bugs at a
fraction of the cost of the full Cartesian product.

The generator is constraint-aware: candidates and target pairs are drawn only
from valid combinations, so impossible pairs (e.g. SQLite + a Go backend) are
never required. It is deterministic (greedy set-cover with stable tie-breaking)
so parametrized test ids stay stable.
"""

from __future__ import annotations

import itertools


def all_valid_combos(axes, option_ids, is_valid):
    """Every valid full selection (cheap: dict building + validation only)."""
    combos = []
    for values in itertools.product(*(option_ids[axis] for axis in axes)):
        selection = dict(zip(axes, values))
        if is_valid(selection):
            combos.append(selection)
    return combos


def _pairs(selection, axes):
    """The set of cross-axis (axis_i, val_i, axis_j, val_j) pairs in a selection."""
    return {
        (axes[i], selection[axes[i]], axes[j], selection[axes[j]])
        for i in range(len(axes))
        for j in range(i + 1, len(axes))
    }


def pairwise_combos(axes, option_ids, is_valid):
    """A small, deterministic set of valid combos covering every satisfiable pair."""
    valid = all_valid_combos(axes, option_ids, is_valid)
    targets = set().union(*(_pairs(c, axes) for c in valid)) if valid else set()

    selected, covered, remaining = [], set(), list(valid)
    while covered != targets:
        # Pick the combo covering the most still-uncovered pairs (first wins ties).
        best, best_gain = None, 0
        for combo in remaining:
            gain = len(_pairs(combo, axes) - covered)
            if gain > best_gain:
                best, best_gain = combo, gain
        if best is None:
            break
        selected.append(best)
        covered |= _pairs(best, axes)
        remaining.remove(best)
    return selected
