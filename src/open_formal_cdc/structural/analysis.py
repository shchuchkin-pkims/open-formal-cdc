# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Structural CDC analysis on the flat Yosys netlist.

Steps (docs/architecture.md, 4.3):
1. clock domain of every flip-flop (root of its clock pin, mapped to configured clocks);
2. crossings: for every flip-flop, sources from other domains in the combinational
   input cone of its D (and enable) pins, grouped per (source signal, destination signal);
3. scheme of every crossing:
   - mux_enable: destination loads the source data under an enable (recirculating mux
     or flip-flop enable); the enable is reported (Kebaili en_d);
   - ndff / ndff_bus: direct source, chain of >= 2 same-domain flops with single fanout;
     logic before the first stage is reported (glitch candidate);
   - none: anything else;
4. same-clock paths whose source and destination have different reset roots or polarities
   are kept separately as reset_domain crossings;
5. convergence candidates: logic in one domain reading >= 2 synchronizer outputs
   from the same source domain.
The structure only proposes; formal checks decide (ndff_bus gets a Gray check,
mux_enable gets a data-stability check, reset_domain gets an RDC capture check).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..config import Assumption, Check, Clock, Crossing, Endpoint, Input
from .cells import KNOWN_CELLS, CellSpec
from .graph import ASYNC_RESET_PORTS, INV_TYPES, PASS_TYPES, SYNC_RESET_PORTS, Bit, Cell, Graph

LATCH_TYPES = {"$dlatch", "$adlatch", "$dlatchsr", "$_DLATCH_P_", "$_DLATCH_N_"}
# output bit i depends only on bit i of the operands (and the select of a mux)
BITWISE = {"$and", "$or", "$xor", "$xnor", "$not", "$pos", "$buf", "$mux",
           "$_AND_", "$_OR_", "$_XOR_", "$_XNOR_", "$_NOT_", "$_BUF_", "$_MUX_"}

ASYNC = "async"


@dataclass
class Source:
    kind: str          # ff | input
    signal: str        # flip-flop signal or input port
    domain: str
    cell: str | None = None


@dataclass
class StructCrossing:
    name: str
    src: str
    src_domain: str
    dst: str
    dst_domain: str
    src_clock: str | None = None          # configured clock names (for checks)
    dst_clock: str | None = None
    src_line: int | None = None
    dst_line: int | None = None
    bits: list[tuple[int, int]] = field(default_factory=list)   # (source bit, destination bit)
    scheme: str = "none"
    stages: list[str] = field(default_factory=list)
    enable: str | None = None
    enable_active: str = "high"
    logic: str = "direct"                # direct | inverter | combo
    src_kind: str = "ff"
    src_width: int = 1                   # width of the source register, not only used bits
    notes: list[str] = field(default_factory=list)
    latch: str | None = None             # transparent latch on the path
    latch_line: int | None = None
    cell: str | None = None              # synchronizer cell instance (scheme of a library cell)
    cell_type: str | None = None
    stage_cell: str | None = None        # netlist cell of the first synchronizer stage
    d_net: str | None = None             # net on its D input (for the metastability model)
    d_width: int = 0
    second_stage_cell: str | None = None  # second-stage candidate for M5
    second_d_net: str | None = None      # its D input and width
    second_d_width: int = 0
    cone_inputs: list[str] = field(default_factory=list)  # all leaves of the D input cone
    src_reset: str | None = None
    src_reset_active: str = "low"
    dst_reset: str | None = None
    dst_reset_active: str = "low"
    dst_valid: str | None = None
    dst_valid_active: str = "high"


@dataclass
class ResetSignalCrossing:
    name: str
    src: str
    src_clock: str | None
    dst_clock: str | None
    active: str
    consumers: list[str] = field(default_factory=list)
    dst_line: int | None = None
    sync: bool = False


@dataclass
class ResetChain:
    reset: str
    clock: str | None
    head: str
    tail: str
    consumers: list[str] = field(default_factory=list)
    line: int | None = None
    consumer_clock: str | None = None
    consumer_resets: dict[str, str | None] = field(default_factory=dict)
    raw_consumers: list[str] = field(default_factory=list)


@dataclass
class ResetDomainMiss:
    reset: str
    missing: list[str] = field(default_factory=list)
    chains: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    line: int | None = None


@dataclass
class ResetDualUse:
    src: str
    async_user: str
    sync_users: list[str] = field(default_factory=list)
    line: int | None = None


@dataclass
class ResetStuck:
    head: str
    consumers: list[str] = field(default_factory=list)
    reset: str | None = None
    reset_active: str = "low"
    value: int = 0
    line: int | None = None


@dataclass
class ResetLogic:
    kind: str
    cell: str
    dst: str
    sources: list[str] = field(default_factory=list)
    line: int | None = None


@dataclass
class ResetPolarity:
    kind: str
    src: str
    dst: str
    expected: str
    actual: str
    reset: str
    reset_active: str
    value: int | None
    line: int | None = None


@dataclass
class ClockMux:
    name: str
    output: str
    select: str
    clocks: list[str] = field(default_factory=list)
    cell: str | None = None
    line: int | None = None
    select_static: bool = False
    select_d: str | None = None
    on: str | None = None
    on0: int = 0
    on1: int = 0
    protocol: str | None = None


@dataclass
class M5Target:
    crossing: str
    first_cell: str
    first_d: str
    second_cell: str
    second_d: str
    second_dst: str
    clock: str | None
    width: int
    cell_width: int = 0
    remaining_d: str | None = None


def _m5_params(t: M5Target) -> dict:
    params = {"first_cell": t.first_cell, "first_d": t.first_d,
              "second_cell": t.second_cell, "second_d": t.second_d,
              "width": t.width, "clock": t.clock}
    if t.remaining_d:
        params.update({"cell_width": t.cell_width, "remaining_d": t.remaining_d})
    return params


@dataclass
class Structure:
    domains: dict[str, str]                       # flip-flop signal -> domain
    crossings: list[StructCrossing]
    convergence: list[dict]
    warnings: list[str]
    counts: dict[str, int]
    divergence: list[dict] = field(default_factory=list)
    handshakes: list[dict] = field(default_factory=list)
    mem_domains: dict[str, str] = field(default_factory=dict)  # memory read-data net -> write domain
    mem_read_outputs: dict[str, list[str]] = field(default_factory=dict)  # MEMID -> public aliases
    reset_crossings: list[StructCrossing] = field(default_factory=list)  # same-clock reset-domain paths
    reset_signals: list[ResetSignalCrossing] = field(default_factory=list)  # reset released in another clock domain
    clock_muxes: list[ClockMux] = field(default_factory=list)  # simple mux cells driving flip-flop clocks
    reset_polarities: list[ResetPolarity] = field(default_factory=list)  # declaration/producer mismatches
    reset_logic: list[ResetLogic] = field(default_factory=list)  # combinational cells on reset pins
    reset_stuck: list[ResetStuck] = field(default_factory=list)  # reset-chain heads tied to asserted values
    reset_chains: list[ResetChain] = field(default_factory=list)  # authored reset synchronizer chains
    reset_domain_misses: list[ResetDomainMiss] = field(default_factory=list)  # raw reset in unsynchronized domains
    reset_dual_uses: list[ResetDualUse] = field(default_factory=list)  # one net with async and sync reset consumers
    m5_targets: list[M5Target] = field(default_factory=list)  # capture pairs, including fanout receivers


def sanitize(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")
    return s if s and not s[0].isdigit() else f"n_{s}"


class Analyzer:
    def __init__(self, g: Graph, clocks: list[Clock], inputs: list[Input], reset_ports: set[str],
                 clock_domain: dict[str, str] | None = None, outputs: dict[str, str] | None = None,
                 cells: dict[str, CellSpec] | None = None):
        self.g = g
        self.clock_of_port = {c.port: c.name for c in clocks}
        # clock name -> domain; clocks of one synchronous group share a domain
        self.clock_domain = {c.name: c.name for c in clocks}
        self.clock_domain.update(clock_domain or {})
        self.input_domain = {i.port: (self.clock_domain.get(i.clock, i.clock) if i.clock else ASYNC)
                             for i in inputs}
        self.input_clock = {i.port: i.clock for i in inputs}
        self.outputs = outputs or {}            # output port -> clock name
        self.cells = {**KNOWN_CELLS, **(cells or {})}
        self.reset_ports = reset_ports
        self.ff_clock: dict[str, str | None] = {}   # cell name -> configured clock name
        self.warnings: list[str] = []
        self._untyped: set[str] = set()
        self._cone_cache: dict = {}
        self._mem_dom: dict[str, str] = {}
        self.generated: set[str] = set()
        self.ff_domain: dict[str, str] = {}      # cell name -> domain
        self.ff_of_bit: dict[Bit, tuple[Cell, int]] = {}
        for c in g.ffs():
            for i, b in enumerate(c.conns.get("Q", [])):
                if isinstance(b, int):
                    self.ff_of_bit[b] = (c, i)

    # ---- clocks and domains ----
    def _root(self, b: Bit, depth: int = 0) -> list[tuple[str, str]]:
        """Roots of a clock net: ('port', name), ('ff', cell) or ('logic', cell)."""
        d = self.g.driver.get(b)
        if d is None or depth > 64:
            return [("const", str(b))]
        if d.kind == "port":
            return [("port", d.name)]
        c = self.g.cells[d.name]
        if c.is_ff:
            return [("ff", c.name)]
        if c.type in PASS_TYPES | INV_TYPES:
            return self._root(c.conns["A"][0], depth + 1)
        if c.type in ("$and", "$_AND_", "$or", "$_OR_", "$logic_and", "$logic_or", "$mux", "$_MUX_"):
            roots = []
            for _, _, ib in c.inputs():
                roots += self._root(ib, depth + 1)
            clk_roots = [r for r in roots if r[0] == "port" and r[1] in self.clock_of_port]
            doms = {self.clock_domain[self.clock_of_port[r[1]]] for r in clk_roots}
            if len(doms) == 1:
                # gated clock, or a clock mux whose legs are all in one domain
                return clk_roots[:1]
            return roots
        return [("logic", c.name)]

    def domain(self, c: Cell) -> str:
        if c.name in self.ff_domain:
            return self.ff_domain[c.name]
        roots = self._root(c.conns["CLK"][0])
        dom = None
        self.ff_clock[c.name] = None
        if len(roots) == 1 and roots[0][0] == "port" and roots[0][1] in self.clock_of_port:
            clk = self.clock_of_port[roots[0][1]]
            self.ff_clock[c.name] = clk
            dom = self.clock_domain[clk]
        elif len(roots) == 1 and roots[0][0] == "ff":
            # divided clock: related to the clock of the dividing flop (as in timing analysis)
            master = self.g.cells[roots[0][1]]
            if master.name == c.name:
                dom = "unknown:self-clocked"
            else:
                dom = self.domain(master)
                self.ff_clock[c.name] = self.ff_clock.get(master.name)
                self.generated.add(self.g.ff_signal(master))
        else:
            dom = "unknown:" + ",".join(f"{k}:{n}" for k, n in roots)
        self.ff_domain[c.name] = dom
        return dom

    # ---- cones ----
    @staticmethod
    def _const(bits) -> bool:
        return all(not isinstance(x, int) for x in bits)

    def _mux_pass(self, c: Cell, port: str, idx: int) -> bool:
        """Data input of a mux whose other data input is constant (reset/clear mux):
        it does not count as logic on the path."""
        if c.type != "$mux" or port not in ("A", "B"):
            return False
        other = c.conns["B" if port == "A" else "A"]
        w = len(c.conns["Y"])
        return self._const(other[idx:idx + 1] if len(other) == w else other)

    def _cone(self, b: Bit, seen: set) -> list[tuple[Source, int, str]]:
        """Leaves of the combinational input cone: (source, bit index, path kind).
        Results are cached per bit (combinational logic is acyclic)."""
        if not isinstance(b, int) or b in seen:
            return []
        if b in self._cone_cache:
            return self._cone_cache[b]
        seen.add(b)
        res = self._cone_uncached(b, seen)
        seen.discard(b)
        self._cone_cache[b] = res
        return res

    def _cone_uncached(self, b: Bit, seen: set) -> list[tuple[Source, int, str]]:
        d = self.g.driver.get(b)
        if d is None:
            return []
        if d.kind == "port":
            if d.name in self.clock_of_port or d.name in self.reset_ports:
                return []
            if d.name not in self.input_domain:
                if d.name not in self._untyped:
                    self._untyped.add(d.name)
                    self.warnings.append(f"input {d.name}: no clock domain declared; not treated as a crossing source")
                return []
            return [(Source("input", d.name, self.input_domain[d.name]), d.index, "direct")]
        c = self.g.cells[d.name]
        if c.is_ff:
            return [(Source("ff", self.g.ff_signal(c), self.domain(c), c.name), d.index, "direct")]
        if c.type in ("$memrd_v2", "$memrd"):
            # read data of a memory: belongs to the domain of the clock that writes it
            memid = str(c.params.get("MEMID", c.name)).lstrip("\\")
            return [(Source("mem", memid, self.mem_domain(memid), c.name), d.index, "direct")]
        if c.type in self.cells:
            spec = self.cells[c.type]
            role = spec.outputs.get(d.port)
            dom = self.cell_domain(c, role) if role else "unknown:cell"
            return [(Source("cell", f"{c.name}.{d.port}", dom, c.name), d.index, "direct")]
        out = []
        for port, _, ib in self._input_bits(c, d.port, d.index):
            for src, idx, kind in self._cone(ib, seen):
                if c.type in LATCH_TYPES:
                    k = kind if kind.startswith("latch:") else f"latch:{c.name}"
                elif kind.startswith("latch:"):
                    k = kind
                elif c.type in PASS_TYPES or self._mux_pass(c, port, d.index):
                    k = kind
                elif c.type in INV_TYPES:
                    k = "inverter" if kind == "direct" else kind
                else:
                    k = "combo"
                out.append((src, idx, k))
        if len(out) > 1:
            uniq = {}
            for src, idx, k in out:
                key = (src.signal, src.kind, idx)
                if key not in uniq or (uniq[key][2] == "direct" and k != "direct"):
                    uniq[key] = (src, idx, k)
            out = list(uniq.values())
        return out

    def mem_domain(self, memid: str) -> str:
        """Domain of the write ports of a memory (the single one, else 'unknown:mem')."""
        if memid not in self._mem_dom:
            doms = set()
            for c in self.g.cells.values():
                if c.type in ("$memwr_v2", "$memwr") and str(c.params.get("MEMID", "")).lstrip("\\") == memid:
                    roots = self._root(c.conns["CLK"][0])
                    if len(roots) == 1 and roots[0][0] == "port" and roots[0][1] in self.clock_of_port:
                        doms.add(self.clock_domain[self.clock_of_port[roots[0][1]]])
                    else:
                        doms.add("unknown:mem")
            self._mem_dom[memid] = doms.pop() if len(doms) == 1 else "unknown:mem"
        return self._mem_dom[memid]

    def cell_domain(self, c: Cell, role: str) -> str:
        """Domain of a library cell clock role (root of the connected clock net)."""
        port = self.cells[c.type].clocks.get(role)
        bits = c.conns.get(port or "", [])
        if not bits:
            return "unknown:cell"
        roots = self._root(bits[0])
        if len(roots) == 1 and roots[0][0] == "port" and roots[0][1] in self.clock_of_port:
            return self.clock_domain[self.clock_of_port[roots[0][1]]]
        if len(roots) == 1 and roots[0][0] == "ff":
            return self.domain(self.g.cells[roots[0][1]])
        return "unknown:" + ",".join(f"{k}:{n}" for k, n in roots)

    def cell_clock(self, c: Cell, role: str) -> str | None:
        port = self.cells[c.type].clocks.get(role)
        bits = c.conns.get(port or "", [])
        if not bits:
            return None
        roots = self._root(bits[0])
        if len(roots) == 1 and roots[0][0] == "port":
            return self.clock_of_port.get(roots[0][1])
        return None

    def _input_bits(self, c: Cell, out_port: str, i: int) -> list[tuple[str, int, Bit]]:
        """Input bits that output bit i of a cell depends on: bit i of the operands for
        bitwise cells, bits 0..i for adders, everything otherwise."""
        def opnd(port: str, upto: int | None = None) -> list[tuple[str, int, Bit]]:
            bits = c.conns.get(port, [])
            signed = str(c.params.get(f"{port}_SIGNED", "0")).strip("0") != ""
            if upto is None:                       # same bit position
                if i < len(bits):
                    return [(port, i, bits[i])]
                return [(port, len(bits) - 1, bits[-1])] if signed and bits else []
            hi = min(upto, len(bits) - 1)
            return [(port, k, bits[k]) for k in range(hi + 1)] + \
                ([(port, len(bits) - 1, bits[-1])] if signed and upto >= len(bits) and bits else [])
        if out_port == "Y" and c.type in BITWISE:
            res = opnd("A") + opnd("B")
            if c.type in ("$mux", "$_MUX_"):
                res += [("S", 0, c.conns["S"][0])]
            return res
        if out_port == "Y" and c.type in ("$add", "$sub", "$neg"):
            return opnd("A", i) + opnd("B", i)
        return c.inputs()

    def cone(self, b: Bit) -> list[tuple[Source, int, str]]:
        return self._cone(b, set())

    def _enable(self, c: Cell, i: int) -> tuple[Bit | None, str, Bit]:
        """Capture enable of bit i of flip-flop c: (select bit, polarity, data bit)."""
        q = c.conns["Q"][i]
        d = c.conns["D"][i]
        if "EN" in c.conns:
            pol = str(c.params.get("EN_POLARITY", "1")).lstrip("0") == "1"
            return c.conns["EN"][0], "high" if pol else "low", d
        for _ in range(4):                               # recirculating mux, a few levels
            m = self.g.drv_cell(d)
            if m is None or m.type != "$mux":
                break
            idx = self.g.driver[d].index
            a, bb, s = m.conns["A"][idx], m.conns["B"][idx], m.conns["S"][0]
            if a == q:
                return s, "high", bb
            if bb == q:
                return s, "low", a
            d = bb if self._crosses(bb) else a
        return None, "high", c.conns["D"][i]

    def _crosses(self, b: Bit) -> bool:
        return bool(self.cone(b))

    def _always_enabled(self, c: Cell) -> bool:
        if "EN" in c.conns:
            active = "1" if str(c.params.get("EN_POLARITY", "1")).lstrip("0") else "0"
            if not all(b == active for b in c.conns["EN"]):
                return False
        for i in range(len(c.conns.get("D", []))):
            enable, polarity, _ = self._enable(c, i)
            if enable is not None and enable != ("1" if polarity == "high" else "0"):
                return False
        return True

    def _record_second_stage(self, x: StructCrossing, first: Cell, second: Cell) -> None:
        if not self._always_enabled(second) or self._reset_net(first) != self._reset_net(second):
            return
        x.second_stage_cell = second.name
        x.second_d_net = self.g.ff_d_signal(second)
        x.second_d_width = len(second.conns.get("D", []))

    def _m5_receivers(self, first: Cell, dom: str) -> list[Cell]:
        """Same-domain capture flops reachable from Q, allowing fanout and one logic cell."""
        found: dict[str, Cell] = {}
        seen: set[tuple[Bit, int]] = set()

        def visit(bit: Bit, depth: int) -> None:
            if (bit, depth) in seen:
                return
            seen.add((bit, depth))
            for name, port, _ in self.g.loads.get(bit, []):
                c = self.g.cells[name]
                if c.is_ff:
                    if (port == "D" and c.name != first.name and self.domain(c) == dom
                            and self._always_enabled(c)
                            and self._reset_net(first) == self._reset_net(c)):
                        found[c.name] = c
                    continue
                if c.type in PASS_TYPES:
                    for _, _, out in c.outputs():
                        visit(out, depth)
                elif depth == 0:
                    outs = [out for _, _, out in c.outputs()]
                    if len(outs) == 1:
                        visit(outs[0], 1)

        for bit in first.conns.get("Q", []):
            visit(bit, 0)
        return [found[name] for name in sorted(found)]

    def _marked_m5_target(self, x: StructCrossing) -> M5Target | None:
        """Packed synchronizer chain: each D stage equals Q of the preceding stage."""
        if x.scheme != "user_cell" or "cdc_sync" not in self.g.marks(x.dst):
            return None
        candidates = [c for c in self.g.ffs() if self.g.ff_signal(c) == x.dst
                      and self.ff_clock.get(c.name) == x.dst_clock]
        if len(candidates) != 1:
            return None
        c = candidates[0]
        d, q = c.conns.get("D", []), c.conns.get("Q", [])
        if len(d) < 2 or len(d) != len(q) or not self._always_enabled(c):
            return None
        width = 0
        for w in range(len(d) // 2, 0, -1):
            if len(d) % w:
                continue
            if all(d[stage + i] == q[stage - w + i]
                   for stage in range(w, len(d), w) for i in range(w)):
                width = w
                break
        if not width:
            return None
        first_d = self.g.net_signal(d[:width])
        second_d = self.g.net_signal(q[:width])
        second_dst = self.g.net_signal(q[width:2 * width])
        remaining_d = self.g.net_signal(d[2 * width:]) if len(d) > 2 * width else None
        if not first_d or not second_d or not second_dst or (len(d) > 2 * width and not remaining_d):
            return None
        x.stage_cell = c.name
        x.d_net, x.d_width = first_d, width
        x.second_stage_cell = c.name
        x.second_d_net, x.second_d_width = second_d, width
        return M5Target(x.name, c.name, first_d, c.name, second_d, second_dst,
                        self.ff_clock.get(c.name), width, len(d), remaining_d)

    def _m5_targets(self, crossings: list[StructCrossing]) -> list[M5Target]:
        out: list[M5Target] = []
        for x in crossings:
            marked = self._marked_m5_target(x)
            if marked:
                out.append(marked)
                continue
            if x.stage_cell:
                first = self.g.cells.get(x.stage_cell)
            else:
                candidates = [c for c in self.g.ffs() if self.g.ff_signal(c) == x.dst
                              and self.ff_clock.get(c.name) == x.dst_clock]
                first = candidates[0] if len(candidates) == 1 else None
            if first is None:
                continue
            first_d = x.d_net or self.g.ff_d_signal(first)
            if not first_d:
                continue
            for second in self._m5_receivers(first, x.dst_domain):
                second_d = self.g.ff_d_signal(second)
                width = len(second.conns.get("D", []))
                if not second_d or width != len(first.conns.get("D", [])):
                    continue
                out.append(M5Target(x.name, first.name, first_d, second.name, second_d,
                                    self.g.ff_signal(second), self.ff_clock.get(second.name), width))
        return sorted(out, key=lambda t: (t.crossing, t.second_cell))

    def _next_stage(self, b: Bit, dom: str) -> tuple[Cell, int] | None:
        """Single same-domain flip-flop directly loaded by bit b (synchronizer chain)."""
        loads = self.g.loads.get(b, [])
        if len(loads) != 1 or b in self.g.out_bits:
            return None
        cell, port, idx = loads[0]
        c = self.g.cells[cell]
        while (c.type in PASS_TYPES and port == "A") or self._mux_pass(c, port, idx):
            nb = c.conns["Y"][idx]
            loads = self.g.loads.get(nb, [])
            if len(loads) != 1 or nb in self.g.out_bits:
                return None
            cell, port, idx = loads[0]
            c = self.g.cells[cell]
        if c.is_ff and port == "D" and self.domain(c) == dom:
            return c, idx
        return None

    def _gated_next_stage(self, b: Bit, dom: str) -> tuple[Cell, int] | None:
        """Same-domain flop reached from b through one combinational cell (gate between
        synchronizer stages)."""
        loads = self.g.loads.get(b, [])
        if len(loads) != 1 or b in self.g.out_bits:
            return None
        cell, _, _ = loads[0]
        c = self.g.cells[cell]
        if c.is_ff or c.type in PASS_TYPES:
            return None
        outs = [ob for _, _, ob in c.outputs()]
        if len(outs) != 1:
            return None
        return self._next_stage(outs[0], dom)

    # ---- main ----
    def run(self) -> Structure:
        groups: dict[tuple[str, str], dict] = {}
        for c in self.g.ffs():
            dst_dom = self.domain(c)
            if dst_dom.startswith("unknown:"):
                self.warnings.append(f"flip-flop {self.g.ff_signal(c)}: clock domain not found ({dst_dom})")
                continue
            for i in range(len(c.conns.get("D", []))):
                en_bit, en_pol, data_bit = self._enable(c, i)
                leaves = self.cone(data_bit)
                # a function of a single source bit cannot glitch (e.g. an OR with zeros)
                single = len({(s.signal, sidx) for s, sidx, _ in leaves}) == 1
                en_leaves = self.cone(en_bit) if isinstance(en_bit, int) else []
                for src, sidx, kind in leaves:
                    rdc = False
                    if src.domain == dst_dom:
                        if src.kind != "ff" or not src.cell:
                            continue
                        src_reset = self._reset_net(self.g.cells[src.cell])
                        dst_reset = self._reset_net(c)
                        if src_reset is None or src_reset == dst_reset:
                            continue
                        rdc = True
                    key = (src.signal, c.name)
                    g = groups.setdefault(key, {"src": src, "cell": c, "bits": [], "kinds": set(),
                                                "en": set(), "en_cross": False, "cone": set(), "rdc": rdc})
                    g["cone"].update(s.signal for s, _, _ in leaves)
                    g["bits"].append((sidx, i))
                    g["kinds"].add("direct" if single and kind == "combo" else kind)
                    if en_bit is not None:
                        g["en"].add((en_bit, en_pol))
                    if any(s.domain != dst_dom for s, _, _ in en_leaves):
                        g["en_cross"] = True
        crossings = [self._classify(g) for g in groups.values()]
        reset_crossings = [x for x in crossings if x.scheme == "reset_domain"]
        crossings = [x for x in crossings if x.scheme != "reset_domain"]
        crossings += self._output_crossings()
        crossings += self._cell_crossings()
        crossings.sort(key=lambda x: (x.dst_domain, x.dst, x.src))
        reset_crossings.sort(key=lambda x: (x.dst_domain, x.dst, x.src))
        conv = self._convergence(crossings)
        counts: dict[str, int] = {}
        for x in crossings:
            counts[x.scheme] = counts.get(x.scheme, 0) + 1
        domains = {self.g.ff_signal(self.g.cells[n]): d for n, d in self.ff_domain.items()}
        mem_domains = {}
        mem_read_outputs = {}
        for c in self.g.cells.values():
            if c.type in ("$memrd_v2", "$memrd"):
                memid = str(c.params.get("MEMID", c.name)).lstrip("\\")
                dom = self.mem_domain(memid)
                for b in c.conns["DATA"]:
                    for name, idx in self.g.bit_names.get(b, []):
                        if not name.startswith("$"):
                            sig = name if len(self.g.netnames[name][0]) == 1 else f"{name}[{idx}]"
                            mem_domains[name] = dom
                            mem_domains[sig] = dom
                            outputs = mem_read_outputs.setdefault(memid, [])
                            for alias in (name, sig):
                                if alias not in outputs:
                                    outputs.append(alias)
        reset_chains = self._reset_chains()
        return Structure(domains, crossings, conv, self.warnings, counts, self._divergence(crossings),
                         self._handshakes(crossings), mem_domains, mem_read_outputs, reset_crossings,
                         self._reset_signals() + self._sync_reset_signals(),
                         self._clock_muxes(), self._reset_polarities(), self._reset_logic(), self._reset_stuck(),
                         reset_chains, self._reset_domain_misses(reset_chains), self._reset_dual_uses(),
                         self._m5_targets(crossings))

    def _handshakes(self, crossings: list[StructCrossing]) -> list[dict]:
        """Request/acknowledge pairs: a single-bit synchronized crossing s->d (request) and
        one d->s (acknowledge) whose source depends on the request synchronizer output.
        Data crossings captured under an enable derived from the request belong to it."""
        out = []
        singles = [x for x in crossings if x.scheme == "ndff" and x.stages and x.src_kind == "ff"
                   and x.logic in ("direct", "inverter")]
        for rq in singles:
            for ak in singles:
                if ak is rq or ak.src_domain != rq.dst_domain or ak.dst_domain != rq.src_domain:
                    continue
                ack_cell = next((c for c in self.g.ffs() if self.g.ff_signal(c) == ak.src), None)
                if ack_cell is None:
                    continue
                cone = {s.signal for b in ack_cell.conns.get("D", []) for s, _, _ in self.cone(b)}
                en, _, _ = self._enable(ack_cell, 0)
                if isinstance(en, int):
                    cone |= {s.signal for s, _, _ in self.cone(en)}
                if not set(rq.stages[1:]) & cone:
                    continue
                # the initiator reacts to the acknowledge: the next request depends on the
                # synchronized acknowledge (directly or through one more flop of its domain)
                if not self._reaches(rq.src, set(ak.stages[1:]), depth=2):
                    continue
                data = [x.name for x in crossings if x.scheme == "mux_enable" and x.src_domain == rq.src_domain
                        and x.dst_domain == rq.dst_domain]
                out.append({"req": rq.src, "ack": ak.stages[-1], "req_crossing": rq.name,
                            "ack_crossing": ak.name, "data": data, "src_clock": rq.src_clock,
                            "req_inputs": self._depends_on_inputs(rq.src),
                            "ack_inputs": self._depends_on_inputs(ak.src)})
        # both directions of one pair can match; the initiator is the side whose request
        # depends on primary inputs while the responder's acknowledge does not
        keep = []
        for h in out:
            rev = next((o for o in out if o["req_crossing"] == h["ack_crossing"]
                        and o["ack_crossing"] == h["req_crossing"]), None)
            if rev is not None and not (h["req_inputs"] and not h["ack_inputs"]):
                continue
            keep.append(h)
        return keep

    def _reaches(self, signal: str, targets: set[str], depth: int) -> bool:
        """The next state of flop 'signal' depends on one of 'targets' within 'depth'
        flop levels of its own domain."""
        cell = next((c for c in self.g.ffs() if self.g.ff_signal(c) == signal), None)
        frontier, seen = ([cell] if cell else []), set()
        for _ in range(depth):
            nxt = []
            for c in frontier:
                if c.name in seen:
                    continue
                seen.add(c.name)
                for b in list(c.conns.get("D", [])) + list(c.conns.get("EN", [])):
                    for src, _, _ in self.cone(b):
                        if src.signal in targets:
                            return True
                        if src.kind == "ff" and src.domain == self.domain(c) and src.cell:
                            nxt.append(self.g.cells[src.cell])
            frontier = nxt
        return False

    def _depends_on_inputs(self, signal: str, depth: int = 6) -> bool:
        """The flop 'signal' depends (through up to 'depth' flops of its domain) on a
        primary input."""
        cell = next((c for c in self.g.ffs() if self.g.ff_signal(c) == signal), None)
        frontier, seen = ([cell] if cell else []), set()
        for _ in range(depth):
            nxt = []
            for c in frontier:
                if c.name in seen:
                    continue
                seen.add(c.name)
                bits = list(c.conns.get("D", [])) + list(c.conns.get("EN", []))
                for b in bits:
                    for src, _, _ in self.cone(b):
                        if src.kind == "input":
                            return True
                        if src.kind == "ff" and src.domain == self.domain(c) and src.cell:
                            nxt.append(self.g.cells[src.cell])
            frontier = nxt
        return False

    def _divergence(self, crossings: list[StructCrossing]) -> list[dict]:
        """One source bit feeding two or more synchronizer chains."""
        by_bit: dict[tuple[str, int], set[str]] = {}
        line: dict[str, int | None] = {}
        for x in crossings:
            if x.scheme in ("ndff", "ndff_bus"):
                for sb, _ in x.bits:
                    by_bit.setdefault((x.src, sb), set()).add(x.name)
                line[x.src] = x.src_line
        out: dict[str, set[str]] = {}
        for (s, _), xs in by_bit.items():
            if len(xs) >= 2:
                out.setdefault(s, set()).update(xs)
        return [{"src": s, "src_line": line[s], "crossings": sorted(xs)} for s, xs in sorted(out.items())]

    def _reset_source(self, b: Bit, active: str, depth: int = 0) -> tuple[str, str, str | None] | None:
        if not isinstance(b, int) or depth > 64:
            return None
        d = self.g.driver.get(b)
        if d is None:
            return None
        if d.kind == "port":
            return (d.name, active, None) if d.name in self.reset_ports else None
        c = self.g.cells[d.name]
        if c.is_ff:
            return self.g.ff_signal(c), active, c.name
        if c.type in PASS_TYPES | INV_TYPES:
            next_active = active
            if c.type in INV_TYPES:
                next_active = "low" if active == "high" else "high"
            return self._reset_source(c.conns["A"][0], next_active, depth + 1)
        return None

    def _reset_net(self, c: Cell | None) -> tuple[str, str] | None:
        if c is None:
            return None
        for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
            bits = c.conns.get(port, [])
            if not bits:
                continue
            polarity = str(c.params.get(f"{port}_POLARITY", "1")).lstrip("0")
            active = "high" if polarity else "low"
            reset = self._reset_source(bits[0], active)
            if reset:
                name, active, _ = reset
                return name, active
        return None

    def _reset_signals(self) -> list[ResetSignalCrossing]:
        groups: dict[tuple[str, str, str | None, bool], ResetSignalCrossing] = {}
        for c in self.g.ffs():
            dst_clock = self.ff_clock.get(c.name)
            for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                bits = c.conns.get(port, [])
                if not bits:
                    continue
                polarity = str(c.params.get(f"{port}_POLARITY", "1")).lstrip("0")
                reset = self._reset_source(bits[0], "high" if polarity else "low")
                if not reset or not reset[2]:
                    continue
                name, active, source_cell = reset
                source = self.g.cells[source_cell]
                if self.domain(source) == self.domain(c):
                    continue
                src_clock = self.ff_clock.get(source_cell)
                key = (name, active, dst_clock, False)
                if key not in groups:
                    groups[key] = ResetSignalCrossing(f"{name}->reset[{dst_clock}]", name,
                                                      src_clock, dst_clock, active, [], c.line)
                consumer = self.g.ff_signal(c)
                if consumer not in groups[key].consumers:
                    groups[key].consumers.append(consumer)
        out = list(groups.values())
        for x in out:
            x.consumers.sort()
        return sorted(out, key=lambda x: x.name)

    def _sync_reset_signals(self, include_same: bool = False) -> list[ResetSignalCrossing]:
        groups: dict[tuple[str, str, str | None, bool], ResetSignalCrossing] = {}
        for c in self.g.ffs():
            dst_clock = self.ff_clock.get(c.name)
            for d in c.conns.get("D", []):
                m = self.g.drv_cell(d)
                if m is None or m.type not in ("$mux", "$_MUX_"):
                    continue
                const_a = self._const(m.conns["A"])
                const_b = self._const(m.conns["B"])
                if const_a == const_b:
                    continue
                active = "low" if const_a else "high"
                sources = [item[0] for item in self.cone(m.conns["S"][0])]
                if include_same:
                    sources += [Source("input", name, self.input_domain.get(name))
                                for kind, name in self._reset_logic_sources(m.conns["S"][0])
                                if kind == "input" and name in self.reset_ports]
                unique = {}
                for src in sources:
                    unique.setdefault((src.signal, src.kind), src)
                for src in unique.values():
                    if src.kind not in ("ff", "input"):
                        continue
                    if not include_same and (src.kind != "ff" or src.domain == self.domain(c)):
                        continue
                    source = self.g.cells[src.cell] if src.cell else None
                    src_clock = self.ff_clock.get(source.name) if source else self.input_clock.get(src.signal)
                    key = (src.signal, active, dst_clock, True)
                    if key not in groups:
                        groups[key] = ResetSignalCrossing(f"{src.signal}->sync_reset[{dst_clock}]",
                                                          src.signal, src_clock,
                                                          dst_clock, active, [], c.line, True)
                    consumer = self.g.ff_signal(c)
                    if consumer not in groups[key].consumers:
                        groups[key].consumers.append(consumer)
        out = list(groups.values())
        for x in out:
            x.consumers.sort()
        return sorted(out, key=lambda x: x.name)

    def _reset_dual_uses(self) -> list[ResetDualUse]:
        sync_users = {}
        for crossing in self._sync_reset_signals(include_same=True):
            for consumer in crossing.consumers:
                sync_users.setdefault(crossing.src, set()).add(consumer)
        out = []
        for c in self.g.ffs():
            for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                bits = c.conns.get(port, [])
                if not bits:
                    continue
                reset = self._reset_source(bits[0], "high")
                if not reset or reset[0] not in sync_users:
                    continue
                async_user = self.g.ff_signal(c)
                others = sorted(u for u in sync_users[reset[0]] if u != async_user)
                if others:
                    out.append(ResetDualUse(reset[0], async_user, others, c.line))
        return out

    def _reset_value(self, c: Cell, port: str) -> int | None:
        param = {"ARST": "ARST_VALUE", "SRST": "SRST_VALUE", "SET": "SET_VALUE",
                 "CLR": "CLR_VALUE", "ALOAD": "ALOAD_VALUE"}.get(port)
        if port == "ALOAD":
            bits = c.conns.get("AD", [])
            return int(bits[0]) if bits and isinstance(bits[0], str) and bits[0] in ("0", "1") else None
        raw = c.params.get(param) if param else None
        if raw is None:
            return None
        text = str(raw)
        m = re.search(r"([01])$", text)
        return int(m.group(1)) if m else None

    def _reset_chains(self) -> list[ResetChain]:
        out = []
        for c in self.g.ffs():
            for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                bits = c.conns.get(port, [])
                if not bits:
                    continue
                reset = self._reset_source(bits[0], "high")
                if not reset or reset[2] is not None:
                    continue
                consumers = sorted({self.g.ff_signal(self.g.cells[cell])
                                    for bit in c.conns.get("Q", [])
                                    for cell, load_port, _ in self.g.loads.get(bit, [])
                                    if load_port in ASYNC_RESET_PORTS | SYNC_RESET_PORTS})
                if not consumers:
                    continue
                previous = self.g.drv_cell(c.conns.get("D", [None])[0])
                if previous is not None and previous.is_ff:
                    previous_reset = self._reset_net(previous)
                    if not previous_reset or previous_reset[0] != reset[0]:
                        continue
                    head = self.g.ff_signal(previous)
                elif self._const(c.conns["D"]):
                    head = self.g.ff_signal(c)
                else:
                    continue
                consumer_clocks = {self.ff_clock.get(cell)
                                   for bit in c.conns.get("Q", [])
                                   for cell, load_port, _ in self.g.loads.get(bit, [])
                                   if load_port in ASYNC_RESET_PORTS | SYNC_RESET_PORTS}
                consumer_clock = consumer_clocks.pop() if len(consumer_clocks) == 1 else "mixed"
                consumer_resets = {}
                for bit in c.conns.get("Q", []):
                    for cell, load_port, _ in self.g.loads.get(bit, []):
                        if load_port in ASYNC_RESET_PORTS | SYNC_RESET_PORTS:
                            consumer_reset = self._reset_net(self.g.cells[cell])
                            consumer_resets[self.g.ff_signal(self.g.cells[cell])] = \
                                consumer_reset[0] if consumer_reset else None
                out.append(ResetChain(reset[0], self.ff_clock.get(c.name), head,
                                      self.g.ff_signal(c), consumers, c.line, consumer_clock, consumer_resets))
        raw = {}
        for c in self.g.ffs():
            for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                bits = c.conns.get(port, [])
                if bits:
                    source = self._reset_source(bits[0], "high")
                    if source and source[2] is None:
                        raw.setdefault(source[0], set()).add(self.g.ff_signal(c))
        for chain in out:
            chain.raw_consumers = sorted(raw.get(chain.reset, set()) - {chain.head, chain.tail})
        return out

    def _reset_domain_misses(self, chains: list[ResetChain]) -> list[ResetDomainMiss]:
        out = []
        for reset in sorted({x.reset for x in chains}):
            own = [x for x in chains if x.reset == reset]
            chain_domains = {x.clock for x in own}
            members = {x.head for x in own} | {x.tail for x in own}
            missing = {}
            for c in self.g.ffs():
                if self.g.ff_signal(c) in members or self.ff_clock.get(c.name) in chain_domains:
                    continue
                for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                    bits = c.conns.get(port, [])
                    if not bits:
                        continue
                    source = self._reset_source(bits[0], "high")
                    if source and source[0] == reset and source[2] is None:
                        missing.setdefault(self.ff_clock.get(c.name), set()).add(self.g.ff_signal(c))
            if missing:
                consumers = sorted({name for names in missing.values() for name in names})
                line = next((c.line for c in self.g.ffs()
                             if any(self.g.ff_signal(c) in names for names in missing.values())), None)
                out.append(ResetDomainMiss(reset, sorted(missing, key=str), sorted(chain_domains, key=str),
                                           consumers, line))
        return out

    def _reset_stuck(self) -> list[ResetStuck]:
        out = []
        for c in self.g.ffs():
            for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                bits = c.conns.get(port, [])
                if not bits:
                    continue
                value = self._reset_value(c, port)
                if value is None or not c.conns.get("D"):
                    continue
                if not all(str(bit) == str(value) for bit in c.conns["D"]):
                    continue
                polarity = str(c.params.get(f"{port}_POLARITY", "1")).lstrip("0")
                reset = self._reset_source(bits[0], "high" if polarity else "low")
                if not reset:
                    continue
                consumers = set()
                for bit in c.conns.get("Q", []):
                    for cell, load_port, _ in self.g.loads.get(bit, []):
                        consumer = self.g.cells[cell]
                        consumer_reset = self._reset_net(consumer)
                        if (load_port in ASYNC_RESET_PORTS | SYNC_RESET_PORTS
                                or load_port == "D" and consumer_reset and consumer_reset[0] == reset[0]):
                            consumers.add(self.g.ff_signal(consumer))
                consumers = sorted(consumers)
                if consumers:
                    out.append(ResetStuck(self.g.ff_signal(c), consumers, reset[0], reset[1], value, c.line))
        return out

    def _reset_logic_sources(self, b: Bit) -> set[tuple[str, str]]:
        out = set()
        seen = set()

        def visit(bit: Bit) -> None:
            if not isinstance(bit, int) or bit in seen:
                return
            seen.add(bit)
            driver = self.g.driver.get(bit)
            if driver is None:
                return
            if driver.kind == "port":
                out.add(("input", driver.name))
                return
            cell = self.g.cells[driver.name]
            if cell.is_ff:
                out.add(("ff", self.g.ff_signal(cell)))
                return
            for _, _, input_bit in cell.inputs():
                visit(input_bit)

        visit(b)
        return out

    def _reset_logic(self) -> list[ResetLogic]:
        out = []
        for c in self.g.ffs():
            for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                bits = c.conns.get(port, [])
                if not bits:
                    continue
                driver = self.g.driver.get(bits[0])
                if not driver or driver.kind != "cell":
                    continue
                cell = self.g.cells[driver.name]
                if cell.type not in ("$and", "$_AND_", "$or", "$_OR_", "$mux", "$_MUX_"):
                    continue
                sources = self._reset_logic_sources(bits[0])
                if cell.type in ("$mux", "$_MUX_"):
                    kind = "rdc006"
                else:
                    kind = "rdc005" if sum(k == "input" for k, _ in sources) >= 2 else "rdc004"
                out.append(ResetLogic(kind, cell.name, self.g.ff_signal(c),
                                      sorted({name for _, name in sources}), c.line))
        return out

    def _reset_value_source(self, c: Cell) -> tuple[int | None, tuple[str, str, str | None] | None]:
        for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
            bits = c.conns.get(port, [])
            if not bits:
                continue
            polarity = str(c.params.get(f"{port}_POLARITY", "1")).lstrip("0")
            reset = self._reset_source(bits[0], "high" if polarity else "low")
            if reset:
                return self._reset_value(c, port), reset
        return None, None

    def _reset_polarities(self) -> list[ResetPolarity]:
        out = []
        for c in self.g.ffs():
            for port in sorted(ASYNC_RESET_PORTS | SYNC_RESET_PORTS):
                bits = c.conns.get(port, [])
                if not bits:
                    continue
                polarity = str(c.params.get(f"{port}_POLARITY", "1")).lstrip("0")
                active = "high" if polarity else "low"
                reset = self._reset_source(bits[0], active)
                if not reset:
                    continue
                name, _, source_cell = reset
                value = self._reset_value(c, port)
                if source_cell is None:
                    declared = str(self.g.net_attrs.get(name, {}).get("reset_polarity", "")).lower()
                    if declared in ("high", "low") and declared != active:
                        out.append(ResetPolarity("declaration", name, self.g.ff_signal(c),
                                                 declared, active, name, declared, value, c.line))
                    continue
                producer = self.g.cells[source_cell]
                producer_value, producer_reset = self._reset_value_source(producer)
                if producer_reset is None:
                    continue
                if producer_value is not None and producer_value != (1 if active == "high" else 0):
                    out.append(ResetPolarity("producer", self.g.ff_signal(producer),
                                             self.g.ff_signal(c), active,
                                             "high" if producer_value else "low",
                                             producer_reset[0], producer_reset[1], value, c.line))
        return out

    def _clock_root(self, bit: Bit) -> str | None:
        for kind, name in self._root(bit):
            if kind == "port" and name in self.clock_of_port:
                return name
        return None

    def _ff_path_exists(self, src: Bit, dst: Bit, max_depth: int = 4) -> bool:
        seen: set[tuple[Bit, int]] = set()

        def visit(bit: Bit, depth: int) -> bool:
            if bit == src:
                return True
            if depth >= max_depth or (bit, depth) in seen:
                return False
            seen.add((bit, depth))
            d = self.g.driver.get(bit)
            if d is None or d.kind != "cell":
                return False
            c = self.g.cells[d.name]
            if c.is_ff:
                bits = c.conns.get("D", [])
                return bool(bits) and visit(bits[d.index], depth + 1)
            return any(visit(ib, depth) for _, _, ib in c.inputs())

        return visit(dst, 0)

    @staticmethod
    def _reset_active_low(name: str) -> bool:
        n = str(name).lower()
        return n in ("rst", "rst0", "rst1", "reset") or n.endswith(("_n", "_b", "rstn"))

    def _reset_mux_value(self, enable: Bit) -> str | None:
        d = self.g.driver.get(enable)
        if d is None:
            return None
        cell = self.g.cells[d.name]
        if not cell.is_ff:
            return None
        dnet = cell.conns["D"][d.index]
        mux = self.g.drv_cell(dnet)
        if mux is None or mux.type not in ("$mux", "$_MUX_"):
            return None
        select = self.g.bit_name(mux.conns["S"][0])
        if select not in self.reset_ports or not self._reset_active_low(select):
            return None
        return mux.conns["B"][self.g.driver[dnet].index]

    def _andor_clock_mux(self, output_cell: Cell) -> ClockMux | None:
        legs = []
        for bit in output_cell.conns["A"] + output_cell.conns["B"]:
            cell = self.g.drv_cell(bit)
            if cell is None or cell.type not in ("$logic_and", "$_AND_"):
                return None
            ca, cb = self._clock_root(cell.conns["A"][0]), self._clock_root(cell.conns["B"][0])
            if bool(ca) == bool(cb):
                return None
            clock = ca or cb
            enable = cell.conns["B"][0] if ca else cell.conns["A"][0]
            legs.append((clock, enable))
        if len(legs) != 2 or legs[0][0] == legs[1][0] or legs[0][1] == legs[1][1]:
            return None
        enables = [en for _, en in legs]
        common = []
        for c in self.g.ffs():
            for bit in c.conns.get("Q", []):
                if bit not in enables and all(self._ff_path_exists(bit, en) for en in enables):
                    common.append(bit)
        if len(common) != 1:
            return None
        select = common[0]
        if any(not self._ff_path_exists(enables[i], enables[1 - i]) for i in (0, 1)):
            return None
        select_cell_name = self.g.driver[select].name
        select_d = self.g.cells[select_cell_name].conns["D"][self.g.driver[select].index]
        if self.g.driver.get(select_d) is None or self.g.driver[select_d].kind != "port":
            return None
        on = next((name for name, (direction, bits) in self.g.ports.items()
                   if direction == "output" and set(bits) == set(enables)), None)
        if on is None:
            return None
        reset_values = [self._reset_mux_value(en) for en in enables]
        if set(reset_values) != {"0", "1"}:
            return None
        on0 = 1 if reset_values[0] == "1" else 2
        output = self.g.vector_name(output_cell.conns["Y"]) or self.g.bit_name(output_cell.conns["Y"][0])
        return ClockMux(f"{self.g.bit_name(select)}->{output}", output, self.g.bit_name(select),
                        sorted({clk for clk, _ in legs}), output_cell.name, output_cell.line,
                        select_d=self.g.bit_name(select_d), on=on, on0=on0, on1=3 - on0,
                        protocol="andor")

    def _clock_muxes(self) -> list[ClockMux]:
        out = []
        for c in self.g.cells.values():
            if c.type in ("$logic_or", "$_OR_"):
                mux = self._andor_clock_mux(c)
                if mux:
                    out.append(mux)
        for c in self.g.cells.values():
            if c.type not in ("$mux", "$_MUX_"):
                continue
            y = c.conns.get("Y", [])
            if not any(port == "CLK" for b in y for _, port, _ in self.g.loads.get(b, [])):
                continue
            roots_a = {r[1] for r in self._root(c.conns["A"][0])
                       if r[0] == "port" and r[1] in self.clock_of_port}
            roots_b = {r[1] for r in self._root(c.conns["B"][0])
                       if r[0] == "port" and r[1] in self.clock_of_port}
            if len(roots_a) != 1 or len(roots_b) != 1 or roots_a == roots_b:
                continue
            output = self.g.vector_name(y) or self.g.bit_name(y[0])
            select = self.g.bit_name(c.conns["S"][0])
            clocks = sorted(self.clock_of_port[p] for p in roots_a | roots_b)
            out.append(ClockMux(f"{select}->{output}", output, select, clocks, c.name, c.line,
                                "cdc_static" in self.g.marks(select)))
        return sorted(out, key=lambda x: x.name)

    def _classify(self, g: dict) -> StructCrossing:
        src: Source = g["src"]
        c: Cell = g["cell"]
        dst_dom = self.domain(c)
        dst = self.g.ff_signal(c)
        latches = sorted(k[len("latch:"):] for k in g["kinds"] if k.startswith("latch:"))
        kinds = {("combo" if k.startswith("latch:") else k) for k in g["kinds"]}
        logic = "combo" if "combo" in kinds else ("inverter" if "inverter" in kinds else "direct")
        src_cell = self.g.cells[src.cell] if src.cell else None
        if src.kind == "ff" and src_cell:
            src_width = len(src_cell.conns.get("Q", []))
        elif src.signal in self.g.ports:
            src_width = len(self.g.ports[src.signal][1])
        else:
            src_width = len(g["bits"])
        x = StructCrossing(name=f"{src.signal}->{dst}", src=src.signal, src_domain=src.domain, dst=dst,
                           dst_domain=dst_dom, bits=sorted(set(g["bits"])), scheme="none", logic=logic,
                           src_kind=src.kind, src_width=src_width,
                           src_clock=self.ff_clock.get(src.cell) if src_cell else self.input_clock.get(src.signal),
                           dst_clock=self.ff_clock.get(c.name), cone_inputs=sorted(g["cone"]),
                           src_line=src_cell.line if src_cell else None, dst_line=c.line)
        src_reset = self._reset_net(src_cell)
        dst_reset = self._reset_net(c)
        if src_reset:
            x.src_reset, x.src_reset_active = src_reset
        if dst_reset:
            x.dst_reset, x.dst_reset_active = dst_reset
        if len(g["en"]) == 1:
            (en_bit, x.dst_valid_active), = g["en"]
            x.dst_valid = self.g.bit_name(en_bit)
        if g.get("rdc"):
            x.scheme = "reset_domain"
            x.notes.append("data source and destination have different reset domains")
            return x
        if latches:
            lc = self.g.cells[latches[0]]
            x.latch, x.latch_line, x.logic = latches[0], lc.line, "latch"
            x.notes.append(f"transparent latch on the path ({latches[0]}): no resolution time")
            return x
        if src.kind == "mem":
            x.scheme = "async_fifo"
            x.notes.append(f"data read from memory {src.signal} written in {src.domain}: protected by the "
                           "FIFO pointers; declare a 'fifo' check to prove it")
            return x
        marks = self.g.marks(dst) | self.g.marks(src.signal)
        if "cdc_static" in self.g.marks(src.signal):
            x.scheme = "static"
            x.notes.append("source declared static (cdc_static): assumption, verified by a twin check")
            return x
        if "cdc_sync" in marks:
            x.scheme = "user_cell"
            x.notes.append("declared synchronizer (cdc_sync)")
            return x
        if "cdc_gray" in marks and len(x.bits) > 1:
            x.scheme = "gray_bus"
            x.notes.append("declared Gray code (cdc_gray): verified by a Gray check")
            return x
        if "cdc_handshake" in marks:
            x.scheme = "handshake"
            x.notes.append("declared handshake capture (cdc_handshake)")
        if len(g["en"]) == 1 and not g["en_cross"]:
            (en_bit, pol), = g["en"]
            x.scheme = "mux_enable" if x.scheme == "none" else x.scheme
            x.enable = self.g.bit_name(en_bit)
            x.enable_active = pol
            syncs = [s.signal for s, _, _ in self.cone(en_bit)
                     if s.kind == "cell" or (s.kind == "ff" and self._is_sync_output(s.cell))]
            if syncs:
                x.notes.append("enable derived from synchronizer output " + ", ".join(sorted(set(syncs))))
            else:
                x.notes.append("enable is not derived from a synchronizer output")
            return x
        # Synchronizer chain from every destination bit.
        chains = []
        for _, di in x.bits:
            stages = [(c, di)]
            nxt = self._next_stage(c.conns["Q"][di], dst_dom)
            while nxt and len(stages) < 8:
                stages.append(nxt)
                nxt = self._next_stage(nxt[0].conns["Q"][nxt[1]], dst_dom)
            chains.append(stages)
        if chains and all(len(s) >= 2 for s in chains):
            x.stages = [self.g.ff_signal(s[0]) for s in chains[0]]
            x.stage_cell = c.name
            x.d_net = self.g.ff_d_signal(c)
            x.d_width = len(c.conns.get("D", []))
            if len({s[1][0].name for s in chains}) == 1:
                self._record_second_stage(x, c, chains[0][1][0])
            x.scheme = "ndff_bus" if len({d for _, d in x.bits}) > 1 else "ndff"
            if logic == "combo":
                x.notes.append("combinational logic before the first synchronizer stage")
            if len({s for s, _ in x.bits}) != len(x.bits):
                x.notes.append("one source bit drives several synchronizers (divergence)")
            return x
        if x.scheme == "handshake":
            return x
        gated = [self._gated_next_stage(c.conns["Q"][di], dst_dom) for _, di in x.bits]
        if gated and all(gated):
            x.scheme = "ndff_bus" if len(x.bits) > 1 else "ndff"
            x.stages = [dst, self.g.ff_signal(gated[0][0])]
            x.stage_cell = c.name
            x.d_net = self.g.ff_d_signal(c)
            x.d_width = len(c.conns.get("D", []))
            if len({s[0].name for s in gated}) == 1:
                self._record_second_stage(x, c, gated[0][0])
            x.logic = "between_stages"
            x.notes.append("combinational logic between synchronizer stages")
            return x
        x.notes.append("no synchronizer and no enable recognized")
        return x

    def _output_crossings(self) -> list[StructCrossing]:
        """Output ports typed to a clock (set_output_delay) are destinations too."""
        out = []
        for port, clk in self.outputs.items():
            if port not in self.g.ports or self.g.ports[port][0] != "output":
                continue
            dom = self.clock_domain.get(clk, clk)
            per_src: dict[str, list] = {}
            for i, b in enumerate(self.g.ports[port][1]):
                for s, sidx, kind in self.cone(b):
                    if s.domain != dom:
                        per_src.setdefault(s.signal, []).append((s, sidx, i, kind))
            for sig, items in per_src.items():
                s = items[0][0]
                kinds = {k for *_, k in items}
                out.append(StructCrossing(
                    name=f"{sig}->{port}", src=sig, src_domain=s.domain, dst=port, dst_domain=dom,
                    src_clock=self.ff_clock.get(s.cell) if s.cell else self.input_clock.get(sig),
                    dst_clock=clk, src_line=self.g.cells[s.cell].line if s.cell else None, dst_line=None,
                    bits=sorted({(si, di) for _, si, di, _ in items}), scheme="none",
                    logic="combo" if "combo" in kinds else "direct", src_kind=s.kind,
                    notes=["destination is an output port typed to a clock"]))
        return out

    def _cell_crossings(self) -> list[StructCrossing]:
        """Crossings into library synchronizer cells: data through the cell (scheme of the
        cell) and inputs fed from a foreign domain (none)."""
        out = []
        for c in self.g.cells.values():
            spec = self.cells.get(c.type)
            if spec is None:
                continue
            dst_role = "dst" if "dst" in spec.clocks else next(iter(spec.clocks))
            for port, role in spec.inputs.items():
                through = port in spec.through
                dom_role = (("dst" if role == "src" else "src") if through and role else role) or dst_role
                if dom_role not in spec.clocks:
                    dom_role = dst_role
                expect_dom = self.cell_domain(c, role) if role else None
                per_src: dict[str, list] = {}
                for i, b in enumerate(c.conns.get(port, [])):
                    for s, sidx, kind in self.cone(b):
                        per_src.setdefault(s.signal, []).append((s, sidx, i, kind))
                for sig, items in per_src.items():
                    s = items[0][0]
                    unsynced_feed = expect_dom is not None and s.domain != expect_dom
                    if not through and not unsynced_feed:
                        continue
                    if through and not unsynced_feed and s.domain == self.cell_domain(c, dom_role):
                        continue
                    x = StructCrossing(
                        name=f"{sig}->{c.name}.{port}", src=sig, src_domain=s.domain, dst=f"{c.name}.{port}",
                        dst_domain=expect_dom if unsynced_feed else self.cell_domain(c, dom_role),
                        src_clock=self.ff_clock.get(s.cell) if s.kind == "ff" else self.input_clock.get(sig),
                        dst_clock=self.cell_clock(c, role if unsynced_feed else dom_role),
                        src_line=self.g.cells[s.cell].line if s.kind == "ff" else None, dst_line=c.line,
                        bits=sorted({(si, di) for _, si, di, _ in items}), src_kind=s.kind,
                        cell=c.name, cell_type=c.type)
                    if unsynced_feed:
                        x.scheme = "none"
                        x.notes.append(f"input {port} of {c.type} is fed from another domain")
                    else:
                        x.scheme = "user_cell"
                        x.notes.append(f"library synchronizer cell {c.type} (scheme {spec.scheme})")
                    out.append(x)
        return out

    def _is_sync_output(self, cell: str | None) -> bool:
        """Flip-flop that is a later stage of a synchronizer chain (its D comes directly
        from a same-domain flop whose D crosses domains)."""
        if cell is None:
            return False
        c = self.g.cells[cell]
        dom = self.domain(c)
        prev = self.ff_of_bit.get(c.conns["D"][0]) if c.conns.get("D") else None
        if not prev:
            return False
        p, _ = prev
        if self.domain(p) != dom:
            return False
        return any(s.domain != dom for s, _, _ in self.cone(p.conns["D"][0]))

    def _convergence(self, crossings: list[StructCrossing]) -> list[dict]:
        last = {}   # last-stage signal -> (src domain, crossing)
        shared: dict[tuple[str, str], set[str]] = {}
        for x in crossings:
            if x.scheme in ("ndff", "ndff_bus") and x.stages:
                last[x.stages[-1]] = (x.src_domain, x.name)
                shared.setdefault((x.stages[-1], x.src_domain), set()).add(x.name)
        groups = []
        # chains that end in the same (vector) register: recombined synchronizers
        for (at, sd), xs in sorted(shared.items()):
            if len(xs) >= 2:
                dom = next(x.dst_domain for x in crossings if x.name in xs)
                groups.append({"at": at, "domain": dom, "src_domain": sd, "crossings": sorted(xs),
                               "sources": sorted({n.split("->")[0] for n in xs})})
        # synchronizer outputs reaching a flop through up to DEPTH flops of its domain
        # (reconvergence after filters or edge detectors, for example SCL and SDA)
        DEPTH = 3
        reach: dict[str, dict[str, set]] = {}

        def reaching(c: Cell, depth: int) -> dict[str, set]:
            key = f"{c.name}/{depth}"
            if key in reach:
                return reach[key]
            reach[key] = {}
            out: dict[str, set] = {}
            dom = self.domain(c)
            for b in c.conns.get("D", []) + c.conns.get("EN", []):
                for s, _, _ in self.cone(b):
                    if s.kind != "ff" or s.domain != dom:
                        continue
                    if s.signal in last:
                        sd, xn = last[s.signal]
                        out.setdefault(sd, set()).add(xn)
                    elif depth > 1 and s.cell:
                        for sd, xs in reaching(self.g.cells[s.cell], depth - 1).items():
                            out.setdefault(sd, set()).update(xs)
            reach[key] = out
            return out

        sinks = [(self.g.ff_signal(c), self.domain(c), c) for c in self.g.ffs()]
        seen_sets: dict[tuple, int] = {}
        for at, dom, cell in sinks:
            for sd, xs in reaching(cell, DEPTH).items():
                if len(xs) >= 2:
                    key = (sd, tuple(sorted(xs)))
                    seen_sets[key] = seen_sets.get(key, 0) + 1
                    if seen_sets[key] > 2:          # record a source set at its first points only
                        continue
                    srcs = sorted({n.split("->")[0] for n in xs})
                    direct = len(reaching(cell, 1).get(sd, set())) >= 2
                    groups.append({"at": at, "domain": dom, "src_domain": sd, "direct": direct,
                                   "crossings": sorted(xs), "sources": srcs})
        # output ports read directly by the environment
        for port, (d, bits) in self.g.ports.items():
            if d != "output":
                continue
            seen: dict[str, set] = {}
            for b in bits:
                for src, _, _ in self.cone(b):
                    if src.kind == "ff" and src.signal in last:
                        sd, xn = last[src.signal]
                        seen.setdefault(sd, set()).add(xn)
            for sd, xs in seen.items():
                if len(xs) >= 2:
                    groups.append({"at": port, "domain": None, "src_domain": sd, "direct": True,
                                   "crossings": sorted(xs), "sources": sorted({n.split("->")[0] for n in xs})})
        return groups


def analyze(g: Graph, clocks: list[Clock], inputs: list[Input], reset_ports: set[str],
            clock_domain: dict[str, str] | None = None, outputs: dict[str, str] | None = None,
            cells: dict[str, CellSpec] | None = None) -> Structure:
    return Analyzer(g, clocks, inputs, reset_ports, clock_domain, outputs, cells).run()


def to_config(s: Structure, clock_names: set[str], pulse_checks: bool = False,
              pulse_min_edges: int = 2, meta_checks: bool = False, hazard_checks: bool = False,
              hazard_domain_inputs: bool = False, hazard_async: bool = False,
              rdc_checks: bool = False, clock_mux_checks: bool = False,
              m5_checks: bool = False, m5_group: bool = False) -> tuple[list[Crossing], list[Check], list[Assumption]]:
    """Crossings, the checks proposed for them and the assumptions they rely on
    (structure proposes, formal decides)."""
    crossings: list[Crossing] = []
    checks: dict[str, Check] = {}
    assumptions: dict[str, Assumption] = {}
    by_content: dict[str, str] = {}      # identical template + parameters -> one check

    class _Checks(dict):
        def setdefault(self, name, chk):
            key = chk.template + json.dumps(chk.params, sort_keys=True)
            if key in by_content:
                return checks[by_content[key]]
            base, k = name, 2
            while name in checks:               # same name, different content
                name = f"{base}_{k}"
                k += 1
            chk.name = name
            by_content[key] = name
            checks[name] = chk
            return chk

    proposals = _Checks()
    candidates = list(s.crossings) + (list(s.reset_crossings) if rdc_checks else [])
    for x in candidates:
        names: list[str] = []
        anames: list[str] = []
        if x.scheme == "static":
            n = f"static_{sanitize(x.src)}"
            assumptions.setdefault(n, Assumption(n, "static", {"signal": x.src}))
            anames.append(n)
        if x.scheme == "gray_bus" and x.src_kind == "ff" and x.src_clock in clock_names:
            n = f"gray_{sanitize(x.src)}"
            names.append(proposals.setdefault(n, Check(n, "gray", {"signal": x.src, "clock": x.src_clock})).name)
        if x.scheme == "ndff_bus" and x.src_kind == "ff" and x.src_clock in clock_names:
            n = f"gray_{sanitize(x.src)}"
            names.append(proposals.setdefault(n, Check(n, "gray", {"signal": x.src, "clock": x.src_clock})).name)
        if (pulse_checks and x.scheme == "ndff" and x.logic in ("direct", "inverter")
                and x.src_kind == "ff" and x.src_clock in clock_names and x.dst_clock in clock_names):
            n = f"pulse_{sanitize(x.src)}__{sanitize(x.dst)}"
            names.append(proposals.setdefault(n, Check(n, "pulse", {"signal": x.src, "clock": x.dst_clock,
                                                    "src_clock": x.src_clock, "min_edges": pulse_min_edges})).name)
        if (meta_checks and x.scheme == "ndff_bus" and x.logic != "between_stages"
                and x.src_kind == "ff" and x.stage_cell and x.d_net
                and x.src_clock in clock_names and x.dst_clock in clock_names):
            n = f"meta_{sanitize(x.src)}"
            names.append(proposals.setdefault(n, Check(n, "nonew", {
                "src": x.src, "dst": x.stages[-1], "clocks": [x.src_clock, x.dst_clock],
                "msi": [{"cell": x.stage_cell, "d": x.d_net, "width": x.d_width}]})).name)
        if m5_checks and m5_group:
            groups: dict[str, list[M5Target]] = {}
            for t in s.m5_targets:
                if t.clock in clock_names:
                    groups.setdefault(t.clock, []).append(t)
            for clock, targets in groups.items():
                if not any(t.crossing == x.name for t in targets):
                    continue
                targets = sorted({(t.second_cell, t.second_d, t.second_dst): t for t in targets}.values(),
                                 key=lambda t: (t.second_cell, t.second_d, t.second_dst))
                n = f"m5_group_{sanitize(clock)}"
                check = proposals.setdefault(n, Check(n, "settled", {
                    "data": [t.second_d for t in targets], "dst": [t.second_dst for t in targets],
                    "clock": clock, "stable_edges": 2,
                    "m5": [_m5_params(t) for t in targets]}))
                if (x.scheme in ("ndff", "ndff_bus", "user_cell")
                        and any(t.crossing == x.name and t.second_cell == x.second_stage_cell for t in targets)):
                    names.append(check.name)
        elif m5_checks:
            for t in s.m5_targets:
                if t.crossing != x.name or t.clock not in clock_names:
                    continue
                n = f"m5_{sanitize(t.second_dst)}"
                check = proposals.setdefault(n, Check(n, "settled", {
                    "data": t.second_d, "dst": t.second_dst, "clock": t.clock, "stable_edges": 2,
                    "m5": [_m5_params(t)]}))
                if x.scheme in ("ndff", "ndff_bus", "user_cell") and t.second_cell == x.second_stage_cell:
                    names.append(check.name)
        if x.scheme == "mux_enable" and x.dst_clock in clock_names and x.enable:
            n = f"en_{sanitize(x.src)}__{sanitize(x.dst)}"
            names.append(proposals.setdefault(n, Check(n, "en_stable", {"data": x.src, "enable": x.enable,
                                                        "clock": x.dst_clock,
                                                        "enable_active": x.enable_active})).name)
        if (x.scheme in ("ndff", "ndff_bus") and x.logic == "combo"
                and x.dst_clock in clock_names and x.cell is None):
            # T-GLITCH: all foreign-domain sources of the logic in front of this first stage
            srcs = sorted({y.src for y in s.crossings if y.dst == x.dst and y.logic == "combo"})
            n = f"glitch_{sanitize(x.dst)}"
            clocks = sorted({y.src_clock for y in s.crossings if y.dst == x.dst and y.src_clock in clock_names})
            glitch_name = proposals.setdefault(n, Check(n, "onechange", {"signals": srcs, "clocks": clocks})).name
            names.append(glitch_name)
            if hazard_checks and x.d_net:
                members = [y for y in s.crossings if y.dst == x.dst and y.d_net == x.d_net]
                cone_inputs = sorted({n for y in members for n in y.cone_inputs})
                source_clocks = {y.src_clock for y in members if y.src_kind == "ff"}
                kinds = {"ff", "mem"} if hazard_domain_inputs else {"ff"}
                extra_inputs = set(cone_inputs) - {y.src for y in members}
                required_mem = extra_inputs | {y.src for y in members if y.src_kind == "mem"}
                if (members and (hazard_async or all(y.src_domain == x.src_domain for y in members))
                        and all(y.src_kind in kinds for y in members)
                        and (hazard_async and source_clocks <= clock_names
                             or source_clocks == {x.src_clock} and x.src_clock in clock_names)
                        and not {y.src for y in members} - set(cone_inputs)
                        and (not required_mem
                             or (hazard_domain_inputs and required_mem <= set(s.mem_read_outputs)
                                 and (hazard_async or all(any(s.mem_domains.get(alias) == x.src_domain
                                                              for alias in s.mem_read_outputs[n])
                                                          for n in required_mem))))):
                    n = f"hazard_{sanitize(x.dst)}"
                    if hazard_domain_inputs:
                        cone_inputs = sorted((set(cone_inputs) - set(s.mem_read_outputs)
                                              - {y.src for y in members if y.src_kind == "mem"}) |
                                             {sig for sig, dom in s.domains.items()
                                              if hazard_async or dom == x.src_domain} |
                                             {sig for sig, dom in s.mem_domains.items()
                                              if hazard_async or dom == x.src_domain})
                    names.append(proposals.setdefault(n, Check(n, "nohazard", {
                        "d": x.d_net, "inputs": cone_inputs, "clock": x.dst_clock})).name)
                    # M4 refines the sufficient onechange condition. Keep the latter as
                    # a standalone ablation check, but do not let it decide the verdict.
                    names.remove(glitch_name)
        if (rdc_checks and x.src_kind == "ff" and x.src_reset
                and (x.src_reset != x.dst_reset or x.src_reset_active != x.dst_reset_active)
                and x.dst_clock in clock_names):
            n = f"rdc_{sanitize(x.src)}__{sanitize(x.dst)}"
            params = {"src_reset": x.src_reset, "reset_active": x.src_reset_active,
                      "dst_clock": x.dst_clock, "release_cycles": 1,
                      "dst_reset_active": x.dst_reset_active if x.dst_reset else "none"}
            if x.dst_reset:
                params["dst_reset"] = x.dst_reset
            if x.dst_valid:
                params["dst_valid"] = x.dst_valid
                params["valid_active"] = x.dst_valid_active
            names.append(proposals.setdefault(n, Check(n, "rdc_capture", params)).name)
        for g in s.convergence:
            if x.name in g["crossings"]:
                # T-CONV: sources of synchronizers whose outputs meet in one logic cone
                n = f"conv_{sanitize(g['at'])}"
                members = [y for y in s.crossings if y.name in g["crossings"]]
                clocks = sorted({y.src_clock for y in members if y.src_clock in clock_names})
                names.append(proposals.setdefault(n, Check(n, "onechange", {"signals": sorted({y.src for y in members}), "role": "convergence",
                                                            "clocks": clocks})).name)
                if m5_checks:
                    targets = []
                    for y in members:
                        target = next((t for t in s.m5_targets if t.crossing == y.name
                                       and t.second_cell == y.second_stage_cell), None)
                        if (target is None or target.clock not in clock_names or y.src_clock not in clock_names
                                or y.src_width != target.width):
                            targets = []
                            break
                        targets.append(target)
                    if targets:
                        n = f"m5_conv_{sanitize(g['at'])}"
                        pairs = {(t.first_cell, t.second_cell): _m5_params(t) for t in targets}
                        names.append(proposals.setdefault(n, Check(n, "nonew", {
                            "src": [y.src for y in members], "dst": [t.second_dst for t in targets],
                            "clocks": sorted(set(clocks) | {t.clock for t in targets}),
                            "m5": [pairs[key] for key in sorted(pairs)]})).name)
        for h in s.handshakes:
            if x.name in [h["req_crossing"], h["ack_crossing"]] + h["data"] and h["src_clock"] in clock_names:
                n = f"hs_{sanitize(h['req'])}"
                names.append(proposals.setdefault(n, Check(n, "hs_req", {"req": h["req"], "ack": h["ack"],
                                                         "clock": h["src_clock"]})).name)
        src_clk = x.src_clock if x.src_clock in clock_names else None
        dst_clk = x.dst_clock if x.dst_clock in clock_names else None
        crossings.append(Crossing(x.name, Endpoint(x.src, src_clk), Endpoint(x.dst, dst_clk), x.scheme,
                                  names, anames))
    if rdc_checks:
        for r in s.reset_signals:
            if r.dst_clock not in clock_names:
                continue
            n = f"rdc_reset_{sanitize(r.src)}"
            template = "srst_release" if r.sync else "reset_release"
            check = proposals.setdefault(n, Check(n, template, {
                "signal": r.src, "clock": r.dst_clock, "reset_active": r.active}))
            crossings.append(Crossing(r.name, Endpoint(r.src, r.src_clock),
                                      Endpoint("|".join(r.consumers), r.dst_clock),
                                      "reset_domain", [check.name], []))
    if rdc_checks:
        for miss in s.reset_domain_misses:
            n = f"rdc_domain_{sanitize(miss.reset)}"
            crossings.append(Crossing(n, Endpoint(miss.reset, None),
                                      Endpoint("|".join(miss.consumers), None), "reset_domain", [], [],
                                      structural_error=f"missing reset domain for {miss.reset}: synchronized in {', '.join(miss.chains)}, raw in {', '.join(miss.missing)}"))
        missed = {m.reset for m in s.reset_domain_misses}
        for chain in s.reset_chains:
            n = f"rdc_note_{sanitize(chain.tail)}_{sanitize(chain.clock or 'unknown')}"
            if chain.consumer_clock and chain.consumer_clock != chain.clock:
                crossings.append(Crossing(n, Endpoint(chain.tail, chain.clock),
                                          Endpoint("|".join(chain.consumers), chain.consumer_clock),
                                          "reset_domain", [], [],
                                          structural_error=f"reset chain clock {chain.clock} does not match consumer clock {chain.consumer_clock}"))
            else:
                crossings.append(Crossing(n, Endpoint(chain.tail, chain.clock),
                                          Endpoint("|".join(chain.consumers), chain.consumer_clock),
                                          "reset_domain", [], [],
                                          structural_note=f"reset chain {chain.head}->{chain.tail} in {chain.clock}"))
            for consumer in chain.consumers:
                source = chain.consumer_resets.get(consumer)
                if source is None:
                    crossings.append(Crossing(f"rdc_output_{sanitize(consumer)}",
                                              Endpoint(chain.tail, chain.clock), Endpoint(consumer, chain.consumer_clock),
                                              "reset_domain", [], [],
                                              structural_error=f"combinational logic after reset chain tail {chain.tail} drives {consumer}"))
                elif source != chain.tail:
                    crossings.append(Crossing(f"rdc_tap_{sanitize(consumer)}",
                                              Endpoint(source, chain.clock), Endpoint(consumer, chain.consumer_clock),
                                              "reset_domain", [], [],
                                              structural_error=f"consumer {consumer} uses internal reset tap {source} instead of tail {chain.tail}"))
            if chain.reset not in missed:
                for raw in chain.raw_consumers:
                    crossings.append(Crossing(f"rdc_raw_{sanitize(raw)}_{sanitize(chain.tail)}",
                                              Endpoint(chain.reset, None), Endpoint(raw, chain.consumer_clock),
                                              "reset_domain", [], [],
                                              structural_warning=f"raw reset root {chain.reset} is used by {raw} beside reset chain tail {chain.tail}"))
        for r in s.reset_signals:
            if not r.sync and r.src_clock and r.dst_clock and r.src_clock != r.dst_clock:
                for consumer in r.consumers:
                    crossings.append(Crossing(f"rdc_foreign_{sanitize(r.src)}_{sanitize(consumer)}",
                                              Endpoint(r.src, r.src_clock), Endpoint(consumer, r.dst_clock),
                                              "reset_domain", [], [],
                                              structural_error=f"reset source {r.src} from {r.src_clock} drives {consumer} in {r.dst_clock}"))
        for dual in s.reset_dual_uses:
            crossings.append(Crossing(f"rdc_dual_{sanitize(dual.src)}",
                                      Endpoint(dual.src, None), Endpoint(dual.async_user, None),
                                      "reset_domain", [], [],
                                      structural_error=f"reset source {dual.src} has asynchronous and synchronous consumers: "
                                      f"{dual.async_user} and {', '.join(dual.sync_users)}"))
        for stuck in s.reset_stuck:
            n = f"rdc_stuck_{sanitize(stuck.head)}"
            crossings.append(Crossing(n, Endpoint(stuck.head, None),
                                      Endpoint("|".join(stuck.consumers), None), "reset_domain", [], [],
                                      structural_error=f"reset chain head {stuck.head} is tied to asserted value {stuck.value}; downstream reset never releases"))
        for logic in s.reset_logic:
            n = f"rdc_logic_{sanitize(logic.cell)}__{sanitize(logic.dst)}"
            if logic.kind == "rdc004":
                reason = f"combinational reset logic {logic.cell} drives {logic.dst}"
            elif logic.kind == "rdc005":
                reason = f"multiple independent reset sources {', '.join(logic.sources)} drive {logic.dst}"
            elif logic.kind == "rdc006":
                reason = f"muxed reset source {logic.cell} drives {logic.dst} without a local synchronizer"
            else:
                continue
            crossings.append(Crossing(n, Endpoint(logic.cell, None), Endpoint(logic.dst, None),
                                      "reset_domain", [], [], structural_error=reason))
        for p in s.reset_polarities:
            n = f"rdc_polarity_{sanitize(p.src)}__{sanitize(p.dst)}"
            if p.kind == "declaration" or not p.reset or p.value is None:
                crossings.append(Crossing(n, Endpoint(p.src, None), Endpoint(p.dst, None), "reset_domain", [], [],
                                          structural_error=f"{p.kind} reset polarity mismatch: expected {p.expected}, got {p.actual}"))
                continue
            check = proposals.setdefault(n, Check(n, "reset_value", {
                "reset": p.reset, "reset_active": p.reset_active, "dst": p.dst, "value": p.value}))
            crossings.append(Crossing(n, Endpoint(p.src, None), Endpoint(p.dst, None),
                                      "reset_domain", [check.name], []))
    if clock_mux_checks:
        for m in s.clock_muxes:
            n = f"clock_mux_{sanitize(m.output)}"
            check = proposals.setdefault(n, Check(n, "clock_mux", {
                "signal": m.output, "min_steps": 2, "clocks": m.clocks}))
            anames = []
            if m.select_static:
                an = f"static_{sanitize(m.select)}"
                assumptions.setdefault(an, Assumption(an, "static", {"signal": m.select}))
                anames.append(an)
            if m.protocol == "andor":
                an = f"clock_select_{sanitize(m.select)}"
                assumptions.setdefault(an, Assumption(an, "clock_select", {
                    "select_d": m.select_d, "select": m.select, "on": m.on,
                    "on0": m.on0, "on1": m.on1, "verify": False}))
                anames.append(an)
            crossings.append(Crossing(m.name, Endpoint(m.select, None), Endpoint(m.output, None),
                                      "clock_mux", [check.name], anames))
    return crossings, list(checks.values()), list(assumptions.values())
