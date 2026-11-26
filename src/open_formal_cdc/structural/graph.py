# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Bit-level graph of a flat Yosys netlist (write_json after flatten)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Flip-flop cell types and the ports that matter for CDC.
FF_TYPES = {
    "$dff", "$dffe", "$adff", "$adffe", "$aldff", "$aldffe", "$sdff", "$sdffe", "$sdffce",
    "$dffsr", "$dffsre",
}
ASYNC_RESET_PORTS = {"ARST", "ALOAD", "SET", "CLR"}
SYNC_RESET_PORTS = {"SRST"}
# Cells that only pass a bit through (for clock/reset tracing and "direct" paths).
PASS_TYPES = {"$buf", "$pos", "$_BUF_"}
INV_TYPES = {"$not", "$_NOT_"}

Bit = int | str   # int: net bit; str: constant '0', '1', 'x', 'z'


@dataclass
class Cell:
    name: str
    type: str
    params: dict
    conns: dict[str, list[Bit]]
    dirs: dict[str, str]
    attrs: dict = field(default_factory=dict)

    @property
    def src(self) -> str:
        """Source location 'file:line' of the cell, if known."""
        s = str(self.attrs.get("src", "")).split("|")[0]
        m = re.match(r"^(.*?):(\d+)", s)
        return f"{m.group(1).split('/')[-1]}:{m.group(2)}" if m else ""

    @property
    def line(self) -> int | None:
        m = re.match(r"^.*:(\d+)$", self.src)
        return int(m.group(1)) if m else None

    def inputs(self) -> list[tuple[str, int, Bit]]:
        return [(p, i, b) for p, bits in self.conns.items() if self.dirs.get(p) == "input"
                for i, b in enumerate(bits)]

    def outputs(self) -> list[tuple[str, int, Bit]]:
        return [(p, i, b) for p, bits in self.conns.items() if self.dirs.get(p) == "output"
                for i, b in enumerate(bits)]

    @property
    def is_ff(self) -> bool:
        return self.type in FF_TYPES

    def signal_name(self) -> str | None:
        """yosys-slang names flip-flop cells '$driver$<signal>'."""
        if self.name.startswith("$driver$"):
            return self.name[len("$driver$"):]
        return None


@dataclass
class Driver:
    kind: str            # cell | port | const
    name: str            # cell name, port name or constant value
    port: str = ""       # cell output port
    index: int = 0       # bit index in the port


@dataclass
class Graph:
    top: str
    cells: dict[str, Cell]
    ports: dict[str, tuple[str, list[Bit]]]                 # name -> (direction, bits)
    netnames: dict[str, tuple[list[Bit], bool]]             # name -> (bits, hidden)
    net_attrs: dict[str, dict] = field(default_factory=dict)
    out_bits: set = field(default_factory=set)              # bits of output ports
    _ff_sig_cache: dict = field(default_factory=dict)
    driver: dict[Bit, Driver] = field(default_factory=dict)
    loads: dict[Bit, list[tuple[str, str, int]]] = field(default_factory=dict)
    bit_names: dict[Bit, list[tuple[str, int]]] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict, top: str) -> "Graph":
        m = data["modules"][top]
        cells = {}
        for n, c in m.get("cells", {}).items():
            cells[n] = Cell(n, c["type"], c.get("parameters", {}), c.get("connections", {}),
                            c.get("port_directions", {}), c.get("attributes", {}))
        ports = {n: (p["direction"], p["bits"]) for n, p in m.get("ports", {}).items()}
        netnames = {n: (v["bits"], bool(v.get("hide_name", 0))) for n, v in m.get("netnames", {}).items()}
        g = cls(top, cells, ports, netnames)
        g.net_attrs = {n: v.get("attributes", {}) for n, v in m.get("netnames", {}).items()}
        g.out_bits = {b for d, bits in ports.values() if d == "output" for b in bits if isinstance(b, int)}
        for n, (d, bits) in ports.items():
            if d == "input":
                for i, b in enumerate(bits):
                    if isinstance(b, int):
                        g.driver[b] = Driver("port", n, index=i)
        for c in cells.values():
            for p, i, b in c.outputs():
                if isinstance(b, int):
                    g.driver[b] = Driver("cell", c.name, p, i)
            for p, i, b in c.inputs():
                if isinstance(b, int):
                    g.loads.setdefault(b, []).append((c.name, p, i))
        for n, (bits, hidden) in netnames.items():
            for i, b in enumerate(bits):
                if isinstance(b, int):
                    g.bit_names.setdefault(b, []).append((n, i))
        return g

    def ffs(self) -> list[Cell]:
        return [c for c in self.cells.values() if c.is_ff]

    def drv_cell(self, b: Bit) -> Cell | None:
        d = self.driver.get(b)
        return self.cells[d.name] if d and d.kind == "cell" else None

    def bit_name(self, b: Bit) -> str:
        """Readable name of a bit: public net preferred, 'name[i]' for vectors."""
        if not isinstance(b, int):
            return f"1'b{b}"
        cands = self.bit_names.get(b, [])
        def key(t):
            n, _ = t
            hidden = self.netnames[n][1]
            return (hidden, n.startswith("$"), n.count("."), len(n))
        if not cands:
            return f"<bit {b}>"
        n, i = sorted(cands, key=key)[0]
        return n if len(self.netnames[n][0]) == 1 else f"{n}[{i}]"

    def vector_name(self, bits: list[Bit], internal: bool = False) -> str | None:
        """Net name whose bits are exactly 'bits'; internal also allows generated names."""
        best = None
        for n, (nb, hidden) in self.netnames.items():
            if nb == bits and (internal or not n.startswith("$")):
                cand = (hidden, -n.count("."), len(n), n)
                if best is None or cand < best[0]:
                    best = (cand, n)
        return best[1] if best else None

    def ff_signal(self, c: Cell) -> str:
        """Name of the net driven by a flip-flop, usable in checks: the slang driver name
        if it is a net, else a net matching Q, else a slice 'net[hi:lo]' of a wider net
        (for example a field of a struct register)."""
        if c.name in self._ff_sig_cache:
            return self._ff_sig_cache[c.name]
        q = c.conns.get("Q", [])
        name = c.signal_name()
        res = None
        if name and name in self.netnames and self.netnames[name][0] == q:
            res = name
        if res is None:
            res = self.vector_name(q)
        if res is None and q and all(isinstance(b, int) for b in q):
            res = self._slice_name(q)
        if res is None:
            res = name or c.name
        self._ff_sig_cache[c.name] = res
        return res

    def net_signal(self, bits: list[Bit]) -> str | None:
        """Name of a whole net or contiguous slice, allowing generated names as a last resort."""
        name = self.vector_name(bits)
        if name is None and bits and all(isinstance(b, int) for b in bits):
            name = self._slice_name(bits)
        if name is None:
            name = self.vector_name(bits, internal=True)
        if name is None and bits and all(isinstance(b, int) for b in bits):
            name = self._slice_name(bits, internal=True)
        return name

    def ff_d_signal(self, c: Cell) -> str | None:
        """Name of a flip-flop D input, using generated net names as a last resort."""
        return self.net_signal(c.conns.get("D", []))

    def _slice_name(self, bits: list, internal: bool = False) -> str | None:
        """'net[hi:lo]' of a net in which 'bits' are contiguous and ascending."""
        cands = []
        for n, i in self.bit_names.get(bits[0], []):
            nb, hidden = self.netnames[n]
            if (not internal and n.startswith("$")) or nb[i:i + len(bits)] != bits:
                continue
            cands.append((hidden, n.count("."), len(n), n, i))
        if not cands:
            return None
        _, _, _, n, i = sorted(cands)[0]
        hi = i + len(bits) - 1
        return f"{n}[{i}]" if hi == i else f"{n}[{hi}:{i}]"

    def marks(self, signal: str) -> set[str]:
        """CDC attributes on a signal declaration (cdc_sync, cdc_static, cdc_gray,
        cdc_handshake), aliases folded; also the attributes of a net with the same bits."""
        aliases = {"cdc_sync": "cdc_sync", "synchronizer": "cdc_sync", "async_reg": "cdc_sync",
                   "cdc_static": "cdc_static", "quasi_static": "cdc_static",
                   "cdc_gray": "cdc_gray", "gray_code": "cdc_gray",
                   "cdc_handshake": "cdc_handshake", "req_ack_handshake": "cdc_handshake"}
        out: set[str] = set()
        names = [signal]
        if signal in self.netnames:
            bits = self.netnames[signal][0]
            names += [n for n, (b, _) in self.netnames.items() if b == bits and n != signal]
        for n in names:
            for k in self.net_attrs.get(n, {}):
                a = aliases.get(k.lower())
                if a:
                    out.add(a)
        return out
