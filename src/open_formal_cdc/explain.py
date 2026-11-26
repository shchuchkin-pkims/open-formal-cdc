# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Explanation of counterexamples from the trace.

For T-GLITCH / T-CONV (template onechange) the interesting fact is which source
signals change in the failing step; it is read from the checker's 'v' and 'prev'
in the VCD and mapped back to the design nets through the wrapper.
"""

from __future__ import annotations

import re
from pathlib import Path

from .vcdtab import read_vcd


def _wrapper_map(wrapper: str) -> tuple[dict[str, int], dict[str, str]]:
    """Widths of the exposed wires and their design net names."""
    widths: dict[str, int] = {}
    nets: dict[str, str] = {}
    for line in wrapper.splitlines():
        m = re.match(r"\s*wire\s+(?:\[(\d+):0\]\s+)?(ofcdc_s\d+);\s*//\s*(\S+)", line)
        if m:
            widths[m.group(2)] = int(m.group(1)) + 1 if m.group(1) else 1
            nets[m.group(2)] = m.group(3)
    return widths, nets


def _part_width(part: str, widths: dict[str, int]) -> tuple[str, int, int]:
    """(base wire, width, low bit) of a concatenation part like 'w', 'w[3]', 'w[5:2]'."""
    m = re.match(r"^([A-Za-z_][\w$]*)(?:\[(\d+)(?::(\d+))?\])?$", part)
    if not m:
        return part, 1, 0
    base = m.group(1)
    if m.group(2) is None:
        return base, widths.get(base, 1), 0
    hi = int(m.group(2))
    lo = int(m.group(3)) if m.group(3) is not None else hi
    return base, hi - lo + 1, lo


def explain_onechange(job_dir: Path, check: str, trace: str, model: str = "ticks") -> str | None:
    """'a, b' - the design signals that change together in the last step of the trace."""
    wf = Path(job_dir) / f"wrapper_{model}.v"
    if not wf.exists() or not trace or not Path(trace).exists():
        return None
    wrapper = wf.read_text()
    line = next((l for l in wrapper.splitlines() if f" chk_{check} (" in l and "ofcdc_onechange" in l), None)
    if line is None:
        return None
    cat = line.split(".v(", 1)[1].rsplit(")", 2)[0]
    parts = [p.strip() for p in cat.strip("{} ").split(",")]
    widths, nets = _wrapper_map(wrapper)
    names, rows = read_vcd(trace, ["v", "prev"])
    vn = next((n for n in names if n.endswith(f"chk_{check}.v")), None)
    pn = next((n for n in names if n.endswith(f"chk_{check}.prev")), None)
    if not rows or vn is None or pn is None:
        return None
    last = rows[-1][1]
    try:
        diff = int(last[vn], 16) ^ int(last[pn], 16)
    except (KeyError, ValueError):
        return None
    total = sum(_part_width(p, widths)[1] for p in parts)
    pos, changed = total, []
    for p in parts:
        base, w, lo = _part_width(p, widths)
        pos -= w
        bits = (diff >> pos) & ((1 << w) - 1)
        if bits:
            name = nets.get(base, base)
            if lo or w != widths.get(base, w):
                name = f"{name}[{lo + w - 1}:{lo}]" if w > 1 else f"{name}[{lo}]"
            n = bin(bits).count("1")
            changed.append(f"{name} ({n} bit{'s' if n > 1 else ''})")
    return ", ".join(changed) if changed else None
