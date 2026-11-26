# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Prioritize cut refinement by signal activity in a counterexample VCD."""

from __future__ import annotations

from pathlib import Path

from .vcdtab import read_vcd


def activity(trace: str | Path, cuts: list[str]) -> dict[str, tuple[int, int] | None]:
    """(changes in the last step, changes in the whole trace) for every cut."""
    names, rows = read_vcd(trace, cuts)
    out = {}
    for cut in cuts:
        matches = [n for n in names if n == f"u_dut.{cut}"]
        if not matches:
            matches = [n for n in names if n == cut or n.endswith("." + cut)]
        if not matches:
            out[cut] = None
            continue
        name = matches[0]
        values = [row.get(name) for _, row in rows]
        if len(values) < 2:
            out[cut] = (0, 0)
            continue
        changes = sum(b != a for a, b in zip(values, values[1:]))
        last = int(values[-1] != values[-2])
        out[cut] = (last, changes)
    return out


def prioritize(trace: str | Path, cuts: list[str]) -> list[str]:
    """Most recently active cuts first; unknown signals last, stable order for ties."""
    scores = activity(trace, cuts)
    order = {name: i for i, name in enumerate(cuts)}

    def key(name: str):
        score = scores[name]
        if score is None:
            return (1, 0, 0, order[name])
        last, changes = score
        return (0, -last, -changes, order[name])

    return sorted(cuts, key=key)
