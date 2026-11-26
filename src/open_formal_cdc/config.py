# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Run configuration: design, environment (clocks, resets, inputs), checks, variants.

The YAML format is described in docs/config.md. In stage 1 crossings are given by hand
as a list of checks; later the structural analysis will produce them.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TIME_MODELS = ("ticks", "clk2ff")
EXPECT_VALUES = ("proven", "cex", "vacuous")
VERDICTS = ("safe", "safe_assuming", "unsafe", "no_scheme", "structural", "unresolved", "note", "warning")
ASSUMPTION_KINDS = ("constant", "static", "hamming1", "onehot0", "quasi_static", "clock_select")
SCHEMES = ("none", "ndff", "ndff_bus", "gray_bus", "mux_enable", "handshake", "pulse_toggle",
           "async_fifo", "reset_sync", "reset_domain", "clock_mux", "static", "user_cell", "external_sync")


class ConfigError(ValueError):
    """Error in a configuration file."""


@dataclass
class Design:
    top: str
    files: list[Path]
    slang_args: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Clock:
    name: str
    port: str
    period: float | None = None   # ns; used by options.clock_ratio = periods


@dataclass
class Reset:
    port: str
    active_low: bool
    clock: str | None          # domain reset by this reset
    mode: str = "init"         # init: only at start; free: may be asserted at any time


@dataclass
class Input:
    port: str
    clock: str | None          # None: asynchronous input (may change at any step)


@dataclass
class Check:
    name: str
    template: str
    params: dict[str, Any]
    expect: str | None = None  # expected outcome (examples and regression)


@dataclass
class Assumption:
    """Environment assumption. Applied as 'assume' to every check (or to the checks in
    applies_to); if it constrains an internal design net it is also verified by a
    twin job where it is asserted."""
    name: str
    kind: str                  # constant | static | hamming1 | onehot0
    params: dict[str, Any]
    applies_to: list[str] | None = None   # check names; None means all checks
    expect: str | None = None  # expected outcome of the twin job


@dataclass
class Endpoint:
    signal: str
    clock: str | None


@dataclass
class Crossing:
    name: str
    src: Endpoint
    dst: Endpoint
    scheme: str
    checks: list[str]          # checks that prove this crossing
    assumptions: list[str]     # assumptions this crossing relies on directly
    expect: str | None = None  # expected verdict
    structural_error: str | None = None  # exact mismatch found by structural analysis
    structural_warning: str | None = None  # review finding, not a proof of incorrect behavior
    structural_note: str | None = None     # reset-chain record, not a violation


@dataclass
class Options:
    time_models: list[str] = field(default_factory=lambda: ["ticks"])
    reset_steps: int = 4
    cover_depth: int = 40
    timeout: int = 300
    prove_engine: str = "abc pdr"
    cover_engine: str = "smtbmc"
    structural: bool = True    # find crossings and propose checks automatically
    clock_ratio: str = "free"  # free | periods (frequency ratios from clock periods)
    pulse_checks: bool = False # propose T-PULSE for single-bit synchronizers
    pulse_min_edges: int = 2   # destination edges a source value must be held for
    meta_checks: bool = False  # propose T-META (metastability model) for bus synchronizers
    m5_checks: bool = False    # propose settled D-to-Q checks with M5 on two stages
    m5_group: bool = False     # group independent settled checks per receiver clock
    m5_prove_engine: str | None = None  # optional engine only for jobs with an m5 model
    m5_cover_engine: str | None = None
    m5_cover_depth: int | None = None
    msi_ablate: bool = False   # also run each T-META check without the MSI model
    hazard_checks: bool = False  # propose M4 function-hazard checks before synchronizers
    hazard_domain_inputs: bool = False  # include all source-domain flops as an overapproximation
    hazard_async: bool = False  # allow independent source domains in the capture-period model
    rdc_checks: bool = False  # propose reset-domain capture checks for source/destination reset pairs
    clock_mux_checks: bool = False  # propose runt-phase checks for simple clock multiplexers


@dataclass
class Variant:
    name: str
    params: dict[str, Any]
    expect: dict[str, str]     # check name -> expected outcome
    options: dict[str, Any] = field(default_factory=dict)   # overrides of options
    resets: dict[str, dict] = field(default_factory=dict)   # reset port -> overrides (mode)


@dataclass
class Config:
    path: Path
    design: Design
    clocks: list[Clock]
    resets: list[Reset]
    inputs: list[Input]
    checks: list[Check]
    options: Options
    variants: list[Variant]
    assumptions: list[Assumption] = field(default_factory=list)
    crossings: list[Crossing] = field(default_factory=list)
    clock_domains: dict[str, str] = field(default_factory=dict)   # clock -> domain (sync groups)
    cells: list[dict] = field(default_factory=list)               # user synchronizer cells
    outputs: dict[str, str] = field(default_factory=dict)         # output port -> clock

    def clock(self, name: str) -> Clock:
        for c in self.clocks:
            if c.name == name:
                return c
        raise ConfigError(f"unknown clock '{name}'")

    def reset_of(self, clock: str) -> Reset | None:
        for r in self.resets:
            if r.clock == clock:
                return r
        return None


def _req(d: dict, key: str, where: str) -> Any:
    if not isinstance(d, dict) or key not in d:
        raise ConfigError(f"{where}: missing required field '{key}'")
    return d[key]


def _list(d: dict, key: str) -> list:
    v = d.get(key) or []
    if not isinstance(v, list):
        raise ConfigError(f"field '{key}' must be a list")
    return v


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: YAML error: {e}") from e
    return parse_config(raw, path)


def parse_config(raw: dict, path: Path) -> Config:
    base = path.parent
    d = _req(raw, "design", "config")
    files = [(base / Path(str(f)).expanduser()).resolve() for f in d.get("files") or []]
    slang_args = [str(a) for a in d.get("slang_args") or []]
    if d.get("filelist"):
        # plain list of source files (one per line, '#' and '//' comments, paths relative
        # to the list); 'exclude' drops files whose name matches a glob pattern
        import fnmatch
        fl = (base / Path(str(d["filelist"])).expanduser()).resolve()
        if not fl.is_file():
            raise ConfigError(f"design.filelist: file not found: {fl}")
        excl = [str(x) for x in d.get("exclude") or []]
        for line in fl.read_text(encoding="utf-8").splitlines():
            line = line.split("//")[0].split("#")[0].strip()
            if line.startswith("+incdir+"):
                for incdir in line.removeprefix("+incdir+").split("+"):
                    slang_args.append(f"-I{(fl.parent / Path(incdir)).resolve()}")
                continue
            if line.startswith("+define+"):
                slang_args += ["-D" + define for define in line.removeprefix("+define+").split("+")]
                continue
            if not line or line.startswith(("+", "-")):
                continue
            f = (fl.parent / line).resolve()
            if not any(fnmatch.fnmatch(f.name, e) for e in excl):
                files.append(f)
        files += [(base / Path(str(f)).expanduser()).resolve() for f in d.get("extra_files") or []]
    if not files:
        raise ConfigError("design.files: empty file list")
    design = Design(
        top=str(_req(d, "top", "design")),
        files=files,
        slang_args=slang_args,
        params=dict(d.get("params") or {}),
    )

    clocks = []
    sdc_inputs: dict[str, str] = {}
    sdc_outputs: dict[str, str] = {}
    clock_domains: dict[str, str] = {}
    if d.get("sdc"):
        from .sdc import load_sdc
        sdc = load_sdc(base / str(d["sdc"]))
        clocks += [Clock(name=k.name, port=k.port, period=k.period) for k in sdc.clocks if k.port]
        sdc_inputs = dict(sdc.input_clock)
        sdc_outputs = dict(sdc.output_clock)
        if sdc.async_groups:
            clock_domains = sdc.domain_map()
        else:
            clock_domains = sdc.domain_map() if raw.get("clock_groups") is None else {}
    for grp_i, grp in enumerate(raw.get("clock_groups") or []):
        # clocks listed in one group are related (same domain); groups are asynchronous
        for n in grp:
            clock_domains[str(n)] = f"grp{grp_i}"
    for i, c in enumerate(_list(raw, "clocks")):
        name = str(_req(c, "name", f"clocks[{i}]"))
        old = next((k for k in clocks if k.name == name), None)
        clocks = [k for k in clocks if k.name != name]
        period = c.get("period", old.period if old else None)
        clocks.append(Clock(name=name, port=str(c.get("port", name)),
                            period=float(period) if period is not None else None))
    if not clocks:
        raise ConfigError("clocks: at least one clock is required")
    clock_names = {c.name for c in clocks}
    if len(clock_names) != len(clocks):
        raise ConfigError("clocks: duplicate clock names")

    resets = []
    for i, r in enumerate(_list(raw, "resets")):
        active = str(r.get("active", "low"))
        if active not in ("low", "high"):
            raise ConfigError(f"resets[{i}].active: expected low or high")
        mode = str(r.get("mode", "init"))
        if mode not in ("init", "free"):
            raise ConfigError(f"resets[{i}].mode: expected init or free")
        clk = r.get("clock")
        if clk is not None and clk not in clock_names:
            raise ConfigError(f"resets[{i}].clock: unknown clock '{clk}'")
        resets.append(Reset(port=str(_req(r, "port", f"resets[{i}]")),
                            active_low=(active == "low"), clock=clk, mode=mode))

    inputs = [Input(port=p, clock=k) for p, k in sdc_inputs.items() if k in clock_names]
    for i, n in enumerate(_list(raw, "inputs")):
        clk = n.get("clock")
        if clk is not None and clk not in clock_names:
            raise ConfigError(f"inputs[{i}].clock: unknown clock '{clk}'")
        port = str(_req(n, "port", f"inputs[{i}]"))
        inputs = [x for x in inputs if x.port != port]
        inputs.append(Input(port=port, clock=clk))

    checks = []
    for i, c in enumerate(_list(raw, "checks")):
        c = dict(c)
        name = str(_req(c, "name", f"checks[{i}]"))
        template = str(_req(c, "template", f"checks[{i}]"))
        expect = c.pop("expect", None)
        if expect is not None and expect not in EXPECT_VALUES:
            raise ConfigError(f"checks[{i}].expect: expected one of {EXPECT_VALUES}")
        c.pop("name"), c.pop("template")
        checks.append(Check(name=name, template=template, params=c, expect=expect))
    if len({c.name for c in checks}) != len(checks):
        raise ConfigError("checks: duplicate check names")

    o = raw.get("options") or {}
    options = Options(
        time_models=list(o.get("time_models", ["ticks"])),
        reset_steps=int(o.get("reset_steps", 4)),
        cover_depth=int(o.get("cover_depth", 40)),
        timeout=int(o.get("timeout", 300)),
        prove_engine=str(o.get("prove_engine", "abc pdr")),
        cover_engine=str(o.get("cover_engine", "smtbmc")),
        structural=bool(o.get("structural", True)),
        clock_ratio=str(o.get("clock_ratio", "free")),
        pulse_checks=bool(o.get("pulse_checks", False)),
        pulse_min_edges=int(o.get("pulse_min_edges", 2)),
        meta_checks=bool(o.get("meta_checks", False)),
        m5_checks=bool(o.get("m5_checks", False)),
        m5_group=bool(o.get("m5_group", False)),
        m5_prove_engine=o.get("m5_prove_engine"),
        m5_cover_engine=o.get("m5_cover_engine"),
        m5_cover_depth=int(o["m5_cover_depth"]) if o.get("m5_cover_depth") is not None else None,
        msi_ablate=bool(o.get("msi_ablate", False)),
        hazard_checks=bool(o.get("hazard_checks", False)),
        hazard_domain_inputs=bool(o.get("hazard_domain_inputs", False)),
        hazard_async=bool(o.get("hazard_async", False)),
        rdc_checks=bool(o.get("rdc_checks", False)),
        clock_mux_checks=bool(o.get("clock_mux_checks", False)),
    )
    if options.clock_ratio not in ("free", "periods"):
        raise ConfigError("options.clock_ratio: expected free or periods")
    if options.clock_ratio == "periods":
        missing = [k.name for k in clocks if not k.period]
        if missing:
            raise ConfigError(f"options.clock_ratio = periods: no period for clocks {missing}")
    bad = [m for m in options.time_models if m not in TIME_MODELS]
    if bad or not options.time_models:
        raise ConfigError(f"options.time_models: allowed values are {TIME_MODELS}")
    if options.reset_steps < 2:
        raise ConfigError("options.reset_steps: must be at least 2")
    if options.m5_cover_depth is not None and options.m5_cover_depth < 1:
        raise ConfigError("options.m5_cover_depth: must be positive")

    check_names = {c.name for c in checks}
    assumptions = []
    for i, a in enumerate(_list(raw, "assumptions")):
        a = dict(a)
        name = str(_req(a, "name", f"assumptions[{i}]"))
        kind = str(_req(a, "kind", f"assumptions[{i}]"))
        if kind not in ASSUMPTION_KINDS:
            raise ConfigError(f"assumptions[{i}].kind: expected one of {ASSUMPTION_KINDS}")
        applies = a.pop("applies_to", None)
        if applies is not None:
            unknown = [c for c in applies if c not in check_names]
            if unknown:
                raise ConfigError(f"assumptions[{i}].applies_to: unknown checks {unknown}")
        expect = a.pop("expect", None)
        if expect is not None and expect not in EXPECT_VALUES:
            raise ConfigError(f"assumptions[{i}].expect: expected one of {EXPECT_VALUES}")
        a.pop("name"), a.pop("kind")
        assumptions.append(Assumption(name=name, kind=kind, params=a,
                                      applies_to=list(applies) if applies is not None else None,
                                      expect=expect))
    assumption_names = {a.name for a in assumptions}
    if len(assumption_names) != len(assumptions):
        raise ConfigError("assumptions: duplicate names")
    if assumption_names & check_names:
        raise ConfigError(f"names used both as check and assumption: {sorted(assumption_names & check_names)}")

    crossings = []
    for i, x in enumerate(_list(raw, "crossings")):
        name = str(_req(x, "name", f"crossings[{i}]"))
        ends = []
        for side in ("from", "to"):
            e = _req(x, side, f"crossings[{i}]")
            clk = e.get("clock")
            if clk is not None and clk not in clock_names:
                raise ConfigError(f"crossings[{i}].{side}.clock: unknown clock '{clk}'")
            ends.append(Endpoint(signal=str(_req(e, "signal", f"crossings[{i}].{side}")), clock=clk))
        scheme = str(x.get("scheme", "none"))
        if scheme not in SCHEMES:
            raise ConfigError(f"crossings[{i}].scheme: expected one of {SCHEMES}")
        xc = [str(c) for c in x.get("checks") or []]
        xa = [str(a) for a in x.get("assumptions") or []]
        if [c for c in xc if c not in check_names]:
            raise ConfigError(f"crossings[{i}].checks: unknown checks {[c for c in xc if c not in check_names]}")
        if [a for a in xa if a not in assumption_names]:
            raise ConfigError(f"crossings[{i}].assumptions: unknown {[a for a in xa if a not in assumption_names]}")
        if x.get("expect") is not None and x.get("expect") not in VERDICTS:
            raise ConfigError(f"crossings[{i}].expect: expected one of {VERDICTS}")
        crossings.append(Crossing(name=name, src=ends[0], dst=ends[1], scheme=scheme, checks=xc,
                                  assumptions=xa, expect=x.get("expect")))
    if len({x.name for x in crossings}) != len(crossings):
        raise ConfigError("crossings: duplicate names")

    target_names = check_names | assumption_names | {x.name for x in crossings}
    base_expect = {c.name: c.expect for c in checks if c.expect}
    base_expect.update({a.name: a.expect for a in assumptions if a.expect})
    base_expect.update({x.name: x.expect for x in crossings if x.expect})
    variants = [Variant(name="base", params={}, expect=base_expect)]
    for vname, v in (raw.get("variants") or {}).items():
        v = v or {}
        exp = dict(variants[0].expect)
        for k, val in (v.get("expect") or {}).items():
            if k not in target_names and not options.structural:
                raise ConfigError(f"variants.{vname}.expect: unknown check '{k}'")
            if k not in check_names | assumption_names and val not in VERDICTS + EXPECT_VALUES:
                raise ConfigError(f"variants.{vname}.expect.{k}: expected one of {VERDICTS}")
            if k in check_names | assumption_names and val not in EXPECT_VALUES:
                raise ConfigError(f"variants.{vname}.expect.{k}: expected one of {EXPECT_VALUES}")
            exp[k] = val
        if str(vname) == "base":          # 'base' extends the base variant
            variants[0].params.update(v.get("params") or {})
            variants[0].expect = exp
            variants[0].options.update(v.get("options") or {})
        else:
            rs = dict(v.get("resets") or {})
            for port, ov in rs.items():
                if port not in {r.port for r in resets}:
                    raise ConfigError(f"variants.{vname}.resets: unknown reset port '{port}'")
                if set(ov) - {"mode"} or ov.get("mode") not in ("init", "free"):
                    raise ConfigError(f"variants.{vname}.resets.{port}: only 'mode: init|free' can be changed")
            variants.append(Variant(name=str(vname), params=dict(v.get("params") or {}), expect=exp,
                                    options=dict(v.get("options") or {}), resets=rs))

    return Config(path=path, design=design, clocks=clocks, resets=resets, inputs=inputs,
                  checks=checks, options=options, variants=variants, assumptions=assumptions,
                  crossings=crossings, clock_domains=clock_domains, cells=_cells(raw),
                  outputs={p: k for p, k in sdc_outputs.items() if k in clock_names})


def _cells(raw: dict) -> list[dict]:
    out = []
    for i, c in enumerate(_list(raw, "cells")):
        _req(c, "module", f"cells[{i}]")
        clocks = _req(c, "clocks", f"cells[{i}]")
        if not isinstance(clocks, dict) or not clocks:
            raise ConfigError(f"cells[{i}].clocks: expected a map role -> clock port")
        for port, role in (c.get("inputs") or {}).items():
            if role is not None and role not in clocks:
                raise ConfigError(f"cells[{i}].inputs.{port}: unknown clock role '{role}'")
        for port, role in (c.get("outputs") or {}).items():
            if role not in clocks:
                raise ConfigError(f"cells[{i}].outputs.{port}: unknown clock role '{role}'")
        out.append(dict(c))
    return out


def variant_config(cfg: Config, variant: Variant) -> Config:
    """Configuration with the option overrides of a variant."""
    if not variant.options and not variant.resets:
        return cfg
    known = set(Options.__dataclass_fields__)
    bad = [k for k in variant.options if k not in known]
    if bad:
        raise ConfigError(f"variants.{variant.name}.options: unknown options {bad}")
    c = copy.copy(cfg)
    c.options = dataclasses.replace(cfg.options, **variant.options)
    c.resets = [dataclasses.replace(r, **variant.resets.get(r.port, {})) for r in cfg.resets]
    if c.options.clock_ratio == "periods" and any(not k.period for k in c.clocks):
        raise ConfigError(f"variants.{variant.name}: clock_ratio = periods needs a period for every clock")
    return c


def variant_design(cfg: Config, variant: Variant) -> Design:
    """Design with variant parameters applied over the base ones."""
    d = copy.deepcopy(cfg.design)
    d.params.update(variant.params)
    return d
