# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Automatic sequential-focus proposals for property-directed abstraction."""

from __future__ import annotations

import re

from .structural.graph import Bit, Graph


def _bits(g: Graph, signal: str) -> list[Bit]:
    if signal in g.netnames:
        return list(g.netnames[signal][0])
    if signal in g.ports:
        return list(g.ports[signal][1])
    m = re.match(r"^(.*)\[(\d+)(?::(\d+))?\]$", signal)
    if m:
        base = m.group(1)
        bits = _bits(g, base)
        hi = int(m.group(2))
        lo = int(m.group(3)) if m.group(3) is not None else hi
        if lo <= hi and hi < len(bits):
            return bits[lo:hi + 1]
    raise KeyError(f"net '{signal}' not found in '{g.top}'")


def _direct_flops(g: Graph, bits: list[Bit]) -> set[str]:
    out = set()
    for bit in bits:
        driver = g.driver.get(bit)
        if driver and driver.kind == "cell" and g.cells[driver.name].is_ff:
            out.add(driver.name)
    return out


def _cone_flops(g: Graph, bits: list[Bit]) -> set[str]:
    out = set()
    seen = set()

    def visit(bit: Bit) -> None:
        if not isinstance(bit, int) or bit in seen:
            return
        seen.add(bit)
        driver = g.driver.get(bit)
        if driver is None or driver.kind != "cell":
            return
        cell = g.cells[driver.name]
        if cell.is_ff:
            out.add(cell.name)
            return
        for _, _, input_bit in cell.inputs():
            visit(input_bit)

    for bit in bits:
        visit(bit)
    return out


def _names(g: Graph, cells: set[str]) -> list[str]:
    names = []
    for cell_name in cells:
        name = g.ff_signal(g.cells[cell_name])
        if name in g.netnames or name in g.ports:
            names.append(name)
    return sorted(set(names))


def en_stable_cuts(g: Graph, params: dict) -> list[str]:
    """Keep the measured data and direct property supports; cut the remaining enable cone."""
    data_bits = _bits(g, str(params["data"]))
    enable_bits = _bits(g, str(params["enable"]))
    keep = _cone_flops(g, data_bits) | _direct_flops(g, data_bits + enable_bits)
    candidates = _cone_flops(g, enable_bits) - keep
    return _names(g, candidates)


def gray_cuts(g: Graph, params: dict) -> list[str]:
    """Keep the measured bus; cut auxiliary state in its next-state cone."""
    bits = _bits(g, str(params["signal"]))
    keep = _direct_flops(g, bits)
    next_bits = []
    for bit in bits:
        driver = g.driver.get(bit)
        if driver and driver.kind == "cell" and g.cells[driver.name].is_ff:
            next_bits += g.cells[driver.name].conns.get("D", [])
    return _names(g, _cone_flops(g, next_bits) - keep)


def propose_cuts(g: Graph, template: str, params: dict) -> list[str]:
    if template == "en_stable":
        return en_stable_cuts(g, params)
    if template == "gray":
        return gray_cuts(g, params)
    raise KeyError(f"automatic focus does not support template '{template}'")
