# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Table of signal values per step from a VCD trace (counterexamples and covers)."""

from __future__ import annotations

from pathlib import Path


def read_vcd(path: str | Path, wanted: list[str] | None = None) -> tuple[list[str], list[tuple[int, dict]]]:
    """Signals matching 'wanted' (full name, or last name component; all if None) and
    their values at every time stamp."""
    ids: dict[str, str] = {}
    scope: list[str] = []
    rows: list[tuple[int, dict]] = []
    cur: dict[str, str] = {}
    t = None
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("$scope"):
            scope.append(line.split()[2])
        elif line.startswith("$upscope"):
            scope.pop()
        elif line.startswith("$var"):
            p = line.split()
            code, name = p[3], p[4]
            full = ".".join(scope[1:] + [name])
            if wanted is None or any(w == full or full.endswith("." + w) or w == name for w in wanted):
                ids.setdefault(code, full)
        elif line.startswith("#"):
            if t is not None:
                rows.append((t, dict(cur)))
            t = int(line[1:])
        elif line and line[0] in "01xzXZ" and line[1:] in ids:
            cur[ids[line[1:]]] = line[0]
        elif line.startswith(("b", "B")):
            val, code = line[1:].split()
            if code in ids:
                cur[ids[code]] = (hex(int(val, 2)) if set(val) <= {"0", "1"} else val)
    if t is not None:
        rows.append((t, dict(cur)))
    names = sorted(set(ids.values()))
    return names, rows


def table(path: str | Path, wanted: list[str] | None = None) -> str:
    names, rows = read_vcd(path, wanted)
    if not rows:
        return "empty trace"
    step = (rows[1][0] - rows[0][0]) if len(rows) > 1 else 1
    head = ["step"] + [n.split(".")[-1] if sum(m.split(".")[-1] == n.split(".")[-1] for m in names) == 1 else n
                       for n in names]
    body = []
    last = None
    for t, r in rows:
        vals = [r.get(n, "-") for n in names]
        if vals == last:
            continue
        last = vals
        body.append([str(t // step if step else t)] + vals)
    widths = [max(len(x[i]) for x in body + [head]) for i in range(len(head))]
    fmt = lambda r: "  ".join(x.ljust(w) for x, w in zip(r, widths)).rstrip()  # noqa: E731
    return "\n".join([fmt(head)] + [fmt(r) for r in body])
