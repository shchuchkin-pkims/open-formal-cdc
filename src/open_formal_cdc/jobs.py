# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""SBY job for one check: wrapper with the time model and environment, design nets
attached with rename -output, the checker module, and prove/cover tasks per time model.
Verified by the stage 0 experiments (docs/experiments.md).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import templates
from .config import Assumption, Check, Config, Design
from .frontend import read_commands
from .netlist import Netlist

_SIMPLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def vid(name: str) -> str:
    """Verilog identifier (escaped when needed)."""
    return name if _SIMPLE.match(name) else f"\\{name} "


def _bits(w: int) -> str:
    return f"[{w - 1}:0] " if w > 1 else ""


@dataclass
class Job:
    name: str
    dir: Path
    check: Check
    instance: templates.Instance
    exposures: dict[str, str] = field(default_factory=dict)   # net -> port ofcdc_sN
    time_models: list[str] = field(default_factory=list)
    assumes: list[str] = field(default_factory=list)          # assumptions applied
    twin_of: str | None = None                                # assumption verified by this job
    baseline_of: str | None = None                            # T-META check whose MSI model is disabled here


def twin_check(a: Assumption) -> Check:
    """Check that asserts assumption a on the design (T-ENV twin)."""
    return Check(name=a.name, template=f"env_{a.kind}", params={**a.params, "mode": "assert"},
                 expect=a.expect)


def is_environment(a: Assumption, nl: Netlist) -> bool:
    """True if the assumption only constrains top-level inputs, or is declared with
    verify: false (a promise about the environment, for example about software):
    it is not verified on the design."""
    if a.params.get("verify") is False:
        return True
    if a.params.get("signals_match"):
        return False
    nets = a.params.get("signals") or [a.params.get("signal")]
    return all(n in nl.ports and nl.ports[n].direction == "input" for n in nets)


class _Ctx:
    """Template context: wrapper signals."""

    def __init__(self, cfg: Config, netlist: Netlist):
        self.cfg = cfg
        self.nl = netlist
        self.exposures: dict[str, tuple[str, int]] = {}
        self.extra_ports: list[tuple[str, int]] = []      # (port, width) added to the design
        self.extra_designs: list[tuple[str, dict[str, str], list[tuple[str, int]]]] = []

    def clock(self, name: str) -> str:
        self.cfg.clock(name)
        return f"ofcdc_clk_{name}"

    def act(self, clock: str) -> str:
        self.cfg.clock(clock)
        return f"ofcdc_act_{clock}"

    def init_done(self) -> str:
        return "ofcdc_init_done"

    def dut_name(self, net: str) -> str:
        """Name of a net inside the design after exposure (escaped for Verilog)."""
        if net in self.nl.ports:
            return vid(net)
        self.signal(net)
        return self.exposures[net][0]

    def known_nets(self) -> set[str]:
        return set(self.nl.nets) | set(self.nl.ports)

    def top_name(self) -> str:
        return self.nl.top

    def data_inputs(self) -> list[str]:
        excluded = {c.port for c in self.cfg.clocks} | {r.port for r in self.cfg.resets}
        return [p.name for p in self.nl.inputs() if p.name not in excluded]

    def input_ports(self) -> list[str]:
        return [p.name for p in self.nl.inputs()]

    def add_design(self, module: str, outputs: dict[str, str], inputs: list[tuple[str, int]]) -> None:
        self.extra_designs.append((module, outputs, inputs))

    def match(self, pattern: str, exclude: list[str] | None = None) -> list[str]:
        """Nets of the design whose names match a glob pattern."""
        import fnmatch
        ex = exclude or []
        return sorted(n for n in self.nl.nets if fnmatch.fnmatchcase(n, pattern)
                      and not any(fnmatch.fnmatchcase(n, e) for e in ex))

    def edge(self, clock: str) -> str:
        """1 in the global step where the clock has its active edge."""
        self.cfg.clock(clock)
        return f"ofcdc_edge_{clock}"

    def model_param(self) -> str:
        """Localparam of the wrapper: 1 for the tick model, 0 for clk2fflogic."""
        return "OFCDC_TICKS"

    def signal(self, net: str) -> tuple[str, int]:
        m = re.match(r"^(.*)\[(\d+)(?::(\d+))?\]$", net)
        if m and net not in self.nl.nets and net not in self.nl.ports:     # bit or slice of a vector
            base, _ = self.signal(m.group(1))
            hi = int(m.group(2))
            lo = int(m.group(3)) if m.group(3) is not None else hi
            if lo == hi:
                return f"{base}[{hi}]", 1
            return f"{base}[{hi}:{lo}]", hi - lo + 1
        if net in self.nl.ports:                    # top-level port: use the wrapper signal
            p = self.nl.ports[net]
            return (f"ofcdc_out_{net}" if p.direction == "output" else _port_sig(self.cfg, net)), p.width
        if net not in self.exposures:
            width = self.nl.net_width(net)
            self.exposures[net] = (f"ofcdc_s{len(self.exposures)}", width)
        return self.exposures[net]


def _port_sig(cfg: Config, port: str) -> str:
    """Wrapper signal that drives an input port of the design."""
    for c in cfg.clocks:
        if c.port == port:
            return f"ofcdc_clk_{c.name}"
    for r in cfg.resets:
        if r.port == port:
            return f"ofcdc_rstport_{port}"
    return f"ofcdc_in_{port}"


def ratio_bounds(p_fast: float, p_slow: float) -> tuple[int, int]:
    """Number of edges of the faster clock in a half-open interval between two
    consecutive edges of the slower clock (Kapschitz and Ginosar): floor..ceil of the
    period ratio; exactly the ratio when it is an integer."""
    r = p_slow / p_fast
    if abs(r - round(r)) < 1e-9:
        return round(r), round(r)
    return math.floor(r), math.ceil(r)


def ratio_constraints(cfg: Config, event: str) -> list[str]:
    """Assumptions bounding the edges of every faster clock between edges of a slower one.
    Each bound is a necessary condition of real periodic clocks with any phase, so the
    model stays a superset of the real behaviour."""
    out = ["  // Clock ratios from periods: edges of the faster clock between two edges of the slower one."]
    clocks = sorted(cfg.clocks, key=lambda c: c.period)
    for i, f in enumerate(clocks):
        for s in clocks[i + 1:]:
            lo, hi = ratio_bounds(f.period, s.period)
            w = max(2, (hi + 1).bit_length())
            n = f"ofcdc_cnt_{f.name}_{s.name}"
            out += [
                f"  reg [{w - 1}:0] {n} = 0;",
                f"  reg {n}_ok = 1'b0;   // a first edge of {s.name} after reset was seen",
                f"  wire [{w - 1}:0] {n}_now = {n} + ofcdc_edge_{f.name};",
                f"  always @({event}) if (ofcdc_init_done) begin",
                f"    if (ofcdc_edge_{s.name}) begin {n} <= 0; {n}_ok <= 1'b1; end",
                f"    else {n} <= {n}_now;",
                "  end",
                f"  always @(*) if (ofcdc_init_done && {n}_ok && ofcdc_edge_{s.name}) "
                f"assume ({n}_now >= {lo} && {n}_now <= {hi});",
                # the upper bound holds from any moment (the next slow edge comes within one
                # slow period); the lower bound only after a first slow edge (free phase)
                f"  always @(*) if (ofcdc_init_done && !ofcdc_edge_{s.name}) assume ({n}_now <= {hi});",
                f"  always @(*) if (ofcdc_init_done && !{n}_ok && ofcdc_edge_{s.name}) assume ({n}_now <= {hi});",
            ]
    return out


def wrapper(cfg: Config, nl: Netlist, ctx: _Ctx, inst: templates.Instance, model: str) -> str:
    """Wrapper module ofcdc_top for the time model (ticks | clk2ff)."""
    R = cfg.options.reset_steps
    rcw = max(1, R.bit_length())
    clock_ports = {c.port for c in cfg.clocks}
    reset_ports = {r.port for r in cfg.resets}
    in_clock = {i.port: i.clock for i in cfg.inputs}
    data_inputs = [p for p in nl.inputs() if p.name not in clock_ports | reset_ports]
    for c in cfg.clocks:
        if c.port not in nl.ports:
            raise KeyError(f"clock '{c.name}': no port '{c.port}' in '{nl.top}'")
    for r in cfg.resets:
        if r.port not in nl.ports:
            raise KeyError(f"reset: no port '{r.port}' in '{nl.top}'")

    ports: list[str] = []
    body: list[str] = []
    if model == "ticks":
        ports.append("input gclk")
        ports += [f"input tick_{c.name}" for c in cfg.clocks]
    else:
        ports += [f"input clk_{c.name}" for c in cfg.clocks]
    ports += [f"input {_bits(p.width)}in_{p.name}" for p in data_inputs]
    ports += [f"input rstfree_{r.port}" for r in cfg.resets if r.mode == "free"]

    # Initial reset: the first R steps.
    gclk_event = "posedge gclk" if model == "ticks" else "$global_clock"
    body += [
        f"  reg [{rcw - 1}:0] ofcdc_rc = 0;",
        f"  always @({gclk_event}) if (ofcdc_rc != {R}) ofcdc_rc <= ofcdc_rc + 1'b1;",
        f"  wire ofcdc_init_done = (ofcdc_rc == {R});",
    ]
    # Time model.
    if model == "ticks":
        ticks = " | ".join(f"tick_{c.name}" for c in cfg.clocks)
        all_ticks = " & ".join(f"tick_{c.name}" for c in cfg.clocks)
        body += [
            "  // Ticks: at least one domain fires on every step; all of them during reset.",
            f"  always @(*) assume ({ticks});",
            f"  always @(*) if (!ofcdc_init_done) assume ({all_ticks});",
        ]
        for c in cfg.clocks:
            body += [
                f"  reg ofcdc_en_{c.name};   // ICG: formalff -declockgate turns it into an enable",
                f"  always @* if (!gclk) ofcdc_en_{c.name} = tick_{c.name};",
                f"  wire ofcdc_clk_{c.name} = gclk & ofcdc_en_{c.name};",
            ]
    else:
        body.append("  // clk2fflogic: free clocks; during reset they toggle together so that"
                    " synchronous resets take effect.")
        for c in cfg.clocks:
            body += [
                f"  wire ofcdc_clk_{c.name} = clk_{c.name};",
                f"  always @(*) if (!ofcdc_init_done) assume (clk_{c.name} == ofcdc_rc[0]);",
            ]
    # Edge of every clock in the global step and the ratio constraints.
    body.append(f"  localparam OFCDC_TICKS = {1 if model == 'ticks' else 0};")
    for c in cfg.clocks:
        if model == "ticks":
            body.append(f"  wire ofcdc_edge_{c.name} = tick_{c.name};")
        else:
            body += [f"  reg ofcdc_clkq_{c.name} = 1'b0;",
                     f"  always @($global_clock) ofcdc_clkq_{c.name} <= clk_{c.name};",
                     f"  wire ofcdc_edge_{c.name} = clk_{c.name} & !ofcdc_clkq_{c.name};"]
    if cfg.options.clock_ratio == "periods":
        body += ratio_constraints(cfg, gclk_event)
    # Resets.
    for r in cfg.resets:
        act = f"!ofcdc_init_done | rstfree_{r.port}" if r.mode == "free" else "!ofcdc_init_done"
        body.append(f"  wire ofcdc_rstact_{r.port} = {act};")
        val = f"!ofcdc_rstact_{r.port}" if r.active_low else f"ofcdc_rstact_{r.port}"
        body.append(f"  wire ofcdc_rstport_{r.port} = {val};")
    for c in cfg.clocks:
        r = cfg.reset_of(c.name)
        extra = f" & !ofcdc_rstact_{r.port}" if r else ""
        body.append(f"  wire ofcdc_act_{c.name} = ofcdc_init_done{extra};")
    # Inputs: inputs of a domain change only on its edge; the others are asynchronous.
    for p in data_inputs:
        clk = in_clock.get(p.name)
        if clk:
            body += [
                f"  reg {_bits(p.width)}ofcdc_in_{p.name};",
                f"  always @(posedge ofcdc_clk_{clk}) ofcdc_in_{p.name} <= in_{p.name};",
            ]
        else:
            body.append(f"  wire {_bits(p.width)}ofcdc_in_{p.name} = in_{p.name};  // asynchronous input")
    for p in nl.outputs():
        body.append(f"  wire {_bits(p.width)}ofcdc_out_{p.name};")
    for net, (port, w) in ctx.exposures.items():
        body.append(f"  wire {_bits(w)}{port};  // {net}")
    for port, w in ctx.extra_ports:
        body.append(f"  wire {_bits(w)}{port};")
    for _, _, inputs in ctx.extra_designs:
        for port, w in inputs:
            body.append(f"  wire {_bits(w)}{port};")
    # Design instance and optional copies with modified internals.
    conns: list[tuple[str, str]] = []
    for p in nl.ports.values():
        if p.direction == "output":
            conns.append((vid(p.name), f"ofcdc_out_{p.name}"))
        else:
            conns.append((vid(p.name), _port_sig(cfg, p.name)))
    conns += [(port, port) for port, _ in ctx.exposures.values()]
    conns += [(port, port) for port, _ in ctx.extra_ports]
    body.append(f"  {vid(nl.top)} u_dut (\n    " +
                ",\n    ".join(f".{p}({s})" for p, s in conns) + "\n  );")
    for module, outputs, inputs in ctx.extra_designs:
        copied = [(vid(p.name), outputs.get(vid(p.name), _port_sig(cfg, p.name)))
                  for p in nl.ports.values() if p.direction == "input"]
        connected = {p for p, _ in copied}
        copied += [(p, s) for p, s in outputs.items() if p not in connected]
        copied += [(p, p) for p, _ in inputs]
        body.append(f"  {vid(module)} u_{module} (\n    " +
                    ",\n    ".join(f".{p}({s})" for p, s in copied) + "\n  );")
    body.append(inst.verilog)

    head = f"// Generated by open-formal-cdc. Time model: {model}\nmodule ofcdc_top (\n  "
    return head + ",\n  ".join(ports) + "\n);\n" + "\n".join(body) + "\nendmodule\n"


def _sel(net: str) -> str:
    """Yosys selection of a net name (escape characters special to selections)."""
    return re.sub(r"([\[\]\*\?])", r"\\\1", net)


def build_job(cfg: Config, design: Design, nl: Netlist, check: Check, src_files: list[str],
              job_dir: Path, rtl_rel: str, assumptions: list[Assumption] | None = None,
              twin_of: str | None = None, baseline_of: str | None = None) -> Job:
    """Prepare the job directory: wrapper_<model>.v, library files, job.sby.
    assumptions are added as 'assume' constraints."""
    ctx = _Ctx(cfg, nl)
    inst = templates.get(check.template)(check.name, check.params, ctx)
    assumptions = assumptions or []
    for a in assumptions:
        ai = templates.get(f"env_{a.kind}")(a.name, {**a.params, "mode": "assume"}, ctx)
        inst = templates.Instance(
            inst.lib_files + [f for f in ai.lib_files if f not in inst.lib_files],
            inst.verilog + "\n" + ai.verilog, inst.asserts, inst.covers, inst.notes,
            script=inst.script)
    # metastability model (M2a) on the D input of the listed first synchronizer stages
    msi = list(check.params.get("msi") or [])
    msi_lines: list[str] = []
    if msi:
        verilog = [inst.verilog]
        covers = list(inst.covers)
        for k, m in enumerate(msi):
            w = int(m["width"])
            mo, mi = f"ofcdc_mo{k}", f"ofcdc_mi{k}"
            ctx.extra_ports += [(mo, w), (mi, w)]
            msi_lines += [f"rename {m['cell']} ofcdc_msi_ff{k}",
                          f"add -output {mo} {w}", f"add -input {mi} {w}",
                          f"connect -set {mo} {m['d']}", f"connect -port ofcdc_msi_ff{k} D {mi}"]
            verilog += [f"  wire ofcdc_msi_alt{k};",
                        f"  ofcdc_msi_d #(.W({w}), .TICKS(OFCDC_TICKS)) msi_{k} (.msi_en(1'b1), "
                        f".d({mo}), .d_seen({mi}), .msi_alt(ofcdc_msi_alt{k}));",
                        f"  always @(*) if (ofcdc_init_done) c_msi{k}: cover (ofcdc_msi_alt{k});"]
            covers.append(f"c_msi{k}")
        files = inst.lib_files + ([] if "ofcdc_msi_d.v" in inst.lib_files else ["ofcdc_msi_d.v"])
        inst = templates.Instance(files, "\n".join(verilog), inst.asserts, covers, inst.notes,
                                  script=inst.script)
    m5 = list(check.params.get("m5") or [])
    if m5:
        verilog = [inst.verilog]
        covers = list(inst.covers)
        first_cache: dict[tuple, tuple[str, str, str]] = {}
        for k, m in enumerate(m5):
            w = int(m["width"])
            so, si = f"ofcdc_m5so{k}", f"ofcdc_m5si{k}"
            first = f"ofcdc_m5_first_ff{k}"
            clock = str(m["clock"] if "clock" in m else check.params["clock"])
            edge = ctx.edge(clock)
            act = ctx.act(clock)
            key = (m["first_cell"], m["first_d"], w, clock)
            new_first = key not in first_cache
            if m["first_cell"] == m["second_cell"]:
                new_first = True
                fo, fi = f"ofcdc_m5fo{k}", f"ofcdc_m5fi{k}"
                di = f"ofcdc_m5di{k}"
                cw = int(m.get("cell_width", 2 * w))
                if cw > 2 * w and not m.get("remaining_d"):
                    raise ValueError(f"M5 shared cell needs 'remaining_d' when cell_width exceeds {2 * w}")
                ctx.extra_ports += [(fo, w), (fi, w), (so, w), (si, w), (di, cw)]
                msi_lines += [f"rename {m['first_cell']} {first}",
                              f"add -output {fo} {w}", f"add -input {fi} {w}",
                              f"connect -set {fo} {m['first_d']}",
                              f"add -output {so} {w}", f"add -input {si} {w}",
                              f"connect -set {so} {m['second_d']}",
                              f"add -input {di} {cw}", f"connect -port {first} D {di}"]
                if cw > 2 * w:
                    full = f"ofcdc_m5full{k}"
                    ctx.extra_ports.append((full, cw - 2 * w))
                    msi_lines += [f"add -output {full} {cw - 2 * w}", f"connect -set {full} {m['remaining_d']}"]
                    verilog += [f"  wire [{cw - 1}:0] {di};",
                                f"  assign {di} = {{{full}, {si}, {fi}}};"]
                else:
                    verilog += [f"  wire [{cw - 1}:0] {di};", f"  assign {di} = {{{si}, {fi}}};"]
            else:
                if key not in first_cache:
                    fo, fi = f"ofcdc_m5fo{k}", f"ofcdc_m5fi{k}"
                    ctx.extra_ports += [(fo, w), (fi, w)]
                    msi_lines += [f"rename {m['first_cell']} {first}",
                                  f"add -output {fo} {w}", f"add -input {fi} {w}",
                                  f"connect -set {fo} {m['first_d']}", f"connect -port {first} D {fi}"]
                    first_cache[key] = (fo, fi, f"ofcdc_m5_first_alt{k}")
                second = f"ofcdc_m5_second_ff{k}"
                ctx.extra_ports += [(so, w), (si, w)]
                msi_lines += [f"rename {m['second_cell']} {second}",
                              f"add -output {so} {w}", f"add -input {si} {w}",
                              f"connect -set {so} {m['second_d']}", f"connect -port {second} D {si}"]
            fo, fi, first_alt = first_cache.get(key, (fo, fi, f"ofcdc_m5_first_alt{k}"))
            if new_first:
                first_alt = f"ofcdc_m5_first_alt{k}"
                verilog += [f"  wire {first_alt};",
                            f"  ofcdc_msi_d #(.W({w}), .TICKS(OFCDC_TICKS)) m5_first_{k} "
                            f"(.msi_en(1'b1), .d({fo}), .d_seen({fi}), .msi_alt({first_alt}));"]
            verilog += [f"  wire ofcdc_m5_second_alt{k};",
                        f"  ofcdc_msi_propagate #(.W({w}), .TICKS(OFCDC_TICKS)) m5_second_{k} "
                        f"(.cap({edge}), .act({act}), .trigger({fi} ^ {fo}), "
                        f".d({so}), .d_seen({si}), .msi_alt(ofcdc_m5_second_alt{k}));",
                        f"  always @(*) if ({act} && {edge}) c_m5_first{k}: cover ({first_alt});",
                        f"  always @(*) if ({act} && {edge}) c_m5_second{k}: "
                        f"cover (ofcdc_m5_second_alt{k});",
                        f"  always @(*) if ({act} && {edge}) c_m5_pending{k}: "
                        f"cover (ofcdc_m5_second_alt{k} && !{first_alt});"]
            covers += [f"c_m5_first{k}", f"c_m5_second{k}", f"c_m5_pending{k}"]
        files = list(inst.lib_files)
        for name in ("ofcdc_msi_d.v", "ofcdc_msi_propagate.v"):
            if name not in files:
                files.append(name)
        inst = templates.Instance(files, "\n".join(verilog), inst.asserts, covers, inst.notes,
                                  script=inst.script)
    skew = list(check.params.get("skew") or [])
    if skew:
        verilog = [inst.verilog]
        covers = list(inst.covers)
        for k, m in enumerate(skew):
            w = int(m["width"])
            mo, mi = f"ofcdc_sko{k}", f"ofcdc_ski{k}"
            ctx.extra_ports += [(mo, w), (mi, w)]
            cell = f"ofcdc_skew_ff{k}"
            msi_lines += [f"rename {m['cell']} {cell}",
                          f"add -output {mo} {w}", f"add -input {mi} {w}",
                          f"connect -set {mo} {m['d']}", f"connect -port {cell} D {mi}"]
            clock = str(m.get("clock", check.params["clock"]))
            cap = f"{ctx.edge(clock)} & {ctx.act(clock)}"
            verilog += [f"  wire ofcdc_skew_alt{k};",
                        f"  ofcdc_skew_cap #(.W({w})) skew_{k} (.cap({cap}), "
                        f".d({mo}), .d_seen({mi}), .alt(ofcdc_skew_alt{k}));",
                        f"  always @(*) if (ofcdc_init_done) c_skew{k}: cover (ofcdc_skew_alt{k});"]
            covers.append(f"c_skew{k}")
        files = inst.lib_files + ([] if "ofcdc_skew_cap.v" in inst.lib_files else ["ofcdc_skew_cap.v"])
        inst = templates.Instance(files, "\n".join(verilog), inst.asserts, covers, inst.notes,
                                  script=inst.script)
    msi_reset = list(check.params.get("msi_reset") or [])
    if msi_reset:
        verilog = [inst.verilog]
        covers = list(inst.covers)
        for k, m in enumerate(msi_reset):
            mo, mi = f"ofcdc_mro{k}", f"ofcdc_mri{k}"
            ctx.extra_ports += [(mo, 1), (mi, 1)]
            cell = f"ofcdc_msi_rst_ff{k}"
            msi_lines += [f"rename {m['cell']} {cell}",
                          f"add -output {mo} 1", f"add -input {mi} 1",
                          f"connect -set {mo} {m['d']}", f"connect -port {cell} {m['port']} {mi}"]
            active_low = 0 if m.get("active", "low") == "high" else 1
            clock = str(m.get("clock", check.params["clock"]))
            verilog += [f"  wire ofcdc_msi_alt{k};",
                        f"  wire ofcdc_msi_skip{k};",
                        f"  ofcdc_msi_reset #(.ACTIVE_LOW({active_low})) msi_reset_{k} "
                        f"(.clk({ctx.clock(clock)}), .msi_en(1'b1), .rst({mo}), .rst_seen({mi}), "
                        f".msi_alt(ofcdc_msi_alt{k}), .msi_skip(ofcdc_msi_skip{k}));",
                        f"  always @(*) if (ofcdc_init_done) c_msi_reset{k}: cover (ofcdc_msi_alt{k});",
                        f"  always @(*) if (ofcdc_init_done) c_msi_reset_skip{k}: "
                        f"cover (ofcdc_msi_skip{k});"]
            covers += [f"c_msi_reset{k}", f"c_msi_reset_skip{k}"]
        files = inst.lib_files + ([] if "ofcdc_msi_reset.v" in inst.lib_files else ["ofcdc_msi_reset.v"])
        inst = templates.Instance(files, "\n".join(verilog), inst.asserts, covers, inst.notes,
                                  script=inst.script)
    vacuity = list(check.params.get("vacuity") or [])
    if vacuity:
        verilog = [inst.verilog]
        covers = list(inst.covers)
        for k, m in enumerate(vacuity):
            sig, width = ctx.signal(str(m["signal"]))
            clock = str(m["clock"])
            clk = ctx.clock(clock)
            act = ctx.act(clock)
            prev = f"ofcdc_vacuity_prev{k}"
            valid = f"ofcdc_vacuity_valid{k}"
            verilog += [f"  reg {_bits(width)}{prev};",
                        f"  reg {valid} = 1'b0;",
                        f"  always @(posedge {clk}) begin {prev} <= {sig}; {valid} <= {act}; end",
                        f"  always @(*) if ({act} && {valid}) c_vacuity{k}: cover ({sig} != {prev});"]
            covers.append(f"c_vacuity{k}")
        inst = templates.Instance(inst.lib_files, "\n".join(verilog), inst.asserts, covers, inst.notes,
                                  script=inst.script)
    job_dir.mkdir(parents=True, exist_ok=True)
    for old in job_dir.glob("wrapper_*.v"):
        old.unlink()
    for lf in dict.fromkeys(inst.lib_files):
        (job_dir / lf).write_text(templates.lib_text(lf), encoding="utf-8")
    models = cfg.options.time_models
    for m in models:
        (job_dir / f"wrapper_{m}.v").write_text(wrapper(cfg, nl, ctx, inst, m), encoding="utf-8")

    o = cfg.options
    has_m5 = bool(check.params.get("m5"))
    cover_depth = o.m5_cover_depth if has_m5 and o.m5_cover_depth is not None else o.cover_depth
    prove_engine = o.m5_prove_engine if has_m5 and o.m5_prove_engine else o.prove_engine
    cover_engine = o.m5_cover_engine if has_m5 and o.m5_cover_engine else o.cover_engine
    tasks = [f"{m}_{k}" for m in models for k in ("prove", "cover")]
    lines = ["# Generated by open-formal-cdc", f"# check: {check.name} ({check.template})", "", "[tasks]"]
    lines += tasks + ["", "[options]"]
    for m in models:
        lines += [f"{m}_prove: mode prove", f"{m}_cover: mode cover", f"{m}_cover: depth {cover_depth}"]
        if m == "clk2ff":
            lines += [f"{m}_prove: multiclock on", f"{m}_cover: multiclock on"]
    lines += [f"timeout {o.timeout}", "", "[engines]"]
    for m in models:
        lines += [f"{m}_prove: {prove_engine}", f"{m}_cover: {cover_engine}"]
    lines += ["", "[script]"]
    lines += read_commands(design, src_files)
    cut = [str(n) for n in check.params.get("cut") or []]
    cut_mode = str(check.params.get("cut_mode", "value"))
    if cut_mode not in ("value", "state"):
        raise ValueError(f"check '{check.name}': cut_mode must be value or state")
    protected = {c.port for c in cfg.clocks} | {r.port for r in cfg.resets}
    for net in cut:
        if net in protected:
            raise ValueError(f"check '{check.name}': clock/reset port cannot be cut: {net}")
        if net not in nl.nets and net not in nl.ports:
            nl.net_width(net)
    if inst.script:
        # submod skips modules with RTL memories; collect them without changing net names
        lines.append("memory_collect")
    if ctx.exposures or cut or msi_lines or inst.script:
        lines.append(f"cd {design.top}")
        lines += msi_lines
        # 'state' abstracts selected flops at their own clock edges; 'value' is a
        # freer overapproximation. Proofs are sound; counterexamples and covers need
        # confirmation on a refined or full model.
        lines += [f"abstract -{cut_mode} w:{_sel(n)}" for n in cut]
        lines += [f"rename -output {net} {port}" for net, (port, _) in ctx.exposures.items()]
        lines += inst.script
        lines.append("cd ..")
    for m in models:
        for k in ("prove", "cover"):
            lines.append(f"{m}_{k}: read_verilog -formal {' '.join(dict.fromkeys(inst.lib_files))} wrapper_{m}.v")
    # memories become flops: AIGER and SMT witnesses then name the same signals
    lines += ["hierarchy -top ofcdc_top", "proc", "flatten", "memory_collect", "memory_map",
              "setundef -anyseq t:$buf", "opt_clean"]
    for m in models:
        if m == "ticks":
            lines += [f"{m}_prove: formalff -declockgate", f"{m}_cover: formalff -declockgate"]
    lines += ["opt_clean", "", "[files]"]
    lines += [f"{rtl_rel}/{f}" for f in src_files]
    lines += list(dict.fromkeys(inst.lib_files)) + [f"wrapper_{m}.v" for m in models] + [""]
    (job_dir / "job.sby").write_text("\n".join(lines), encoding="utf-8")
    return Job(name=check.name, dir=job_dir, check=check, instance=inst,
               exposures={n: p for n, (p, _) in ctx.exposures.items()}, time_models=models,
               assumes=[a.name for a in assumptions], twin_of=twin_of, baseline_of=baseline_of)
