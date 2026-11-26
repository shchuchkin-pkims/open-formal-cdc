# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Full run: sources -> netlist -> jobs -> SBY -> outcomes -> verdicts -> report."""

from __future__ import annotations

import dataclasses
import json
import shlex
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import __version__
from .config import Assumption, Check, Config, Crossing, variant_config, variant_design
from .executor import Executor
from .explain import explain_onechange
from .frontend import copy_sources, frontend_script
from .jobs import Job, build_job, is_environment, twin_check
from .model import Verdict, assumption_states, crossing_verdict, model_dict
from .netlist import Netlist
from .structural import Graph, Structure, analyze, to_config
from .structural.cells import cell_spec_from_config
from .results import ModelResult, job_results, overall


class FlowError(RuntimeError):
    pass


@dataclass
class CheckOutcome:
    variant: str
    check: str
    template: str
    status: str
    expect: str | None
    models: list[ModelResult] = field(default_factory=list)
    kind: str = "check"                 # check | assumption | msi_baseline
    assumes: list[str] = field(default_factory=list)
    baseline_of: str | None = None       # main T-META check for an MSI-free control run

    @property
    def ok(self) -> bool | None:
        if self.expect is None:
            return None
        return self.status == self.expect


@dataclass
class RunResult:
    outcomes: list[CheckOutcome]
    verdicts: list[Verdict]
    states: dict[str, dict[str, str]]   # variant -> assumption -> state
    structures: dict[str, Structure] = field(default_factory=dict)
    crossings: dict[str, list[Crossing]] = field(default_factory=dict)
    assumptions: dict[str, list[Assumption]] = field(default_factory=dict)
    cell_results: dict[str, RunResult] = field(default_factory=dict)

    @property
    def mismatches(self) -> int:
        return sum(1 for o in self.outcomes if o.ok is False) + sum(1 for v in self.verdicts if v.ok is False)


def _q(p: Path | str) -> str:
    return shlex.quote(str(p))


def run(cfg: Config, out: Path, executor: Executor, parallel: int = 8,
        only: list[str] | None = None, log=print, reuse_from: Path | None = None) -> RunResult:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not cfg.checks and not cfg.assumptions and not cfg.crossings and not cfg.options.structural:
        raise FlowError("nothing to run: no checks, assumptions or crossings")

    cell_verdicts, cell_results = prove_cells(cfg, out, executor, parallel, log)
    if reuse_from is None:
        netlists = frontend(cfg, out, executor, log)
    else:
        netlists = _reuse_frontend(cfg, Path(reuse_from), out, log)
    result = _run_after_frontend(cfg, out, executor, parallel, only, log, netlists, cell_verdicts, cell_results)
    return result


def prove_cells(cfg: Config, out: Path, executor: Executor, parallel: int, log) -> tuple[
        dict[str, tuple[str, list[str]]], dict[str, RunResult]]:
    """T-CELL: every user synchronizer cell ('cells' with prove: true, the default) is
    checked once as a design of its own: clocks and input domains come from its roles,
    crossings inside are found and checked as usual. Returns module -> (verdict, reasons):
    safe if no crossing inside is unsafe or unresolved. Also returns each cell's full run."""
    from .config import parse_config
    res: dict[str, tuple[str, list[str]]] = {}
    runs: dict[str, RunResult] = {}
    for c in cfg.cells:
        if not c.get("prove", True):
            continue
        roles = c["clocks"]
        raw = {
            "design": {"top": c["module"], "files": [str(f) for f in cfg.design.files],
                       "slang_args": cfg.design.slang_args, "params": dict(c.get("params") or {})},
            "clocks": [{"name": r, "port": p} for r, p in roles.items()],
            "resets": [dict(x) for x in c.get("resets") or []],
            # an input without a clock role is asynchronous (the cell synchronizes it)
            "inputs": [{"port": p, "clock": r} for p, r in (c.get("inputs") or {}).items()],
            "options": {"time_models": cfg.options.time_models, "timeout": cfg.options.timeout,
                        "cover_depth": cfg.options.cover_depth, "prove_engine": cfg.options.prove_engine,
                        "cover_engine": cfg.options.cover_engine, "m5_checks": cfg.options.m5_checks},
        }
        sub = parse_config(raw, cfg.path.parent / f"cell_{c['module']}.yaml")
        log(f"[cell] proving synchronizer cell {c['module']}")
        r = run(dataclasses.replace(sub, cells=[]), out / "cells" / c["module"], executor, parallel,
                log=lambda m: log("       " + m))
        runs[c["module"]] = r
        bad = [v for v in r.verdicts if v.verdict in ("unsafe", "no_scheme", "unresolved")]
        if any(v.verdict in ("unsafe", "no_scheme") for v in bad):
            res[c["module"]] = ("unsafe", [f"cell {c['module']}: {v.crossing} {v.verdict}" for v in bad])
        elif bad:
            res[c["module"]] = ("unresolved", [f"cell {c['module']}: {v.crossing} unresolved" for v in bad])
        else:
            res[c["module"]] = ("safe", [f"cell {c['module']} proven ({len(r.verdicts)} crossing(s) inside)"])
    return res, runs


def frontend(cfg: Config, out: Path, executor: Executor, log=print) -> dict[str, Netlist]:
    """Copy sources and build the netlist of every variant (on the executor)."""
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    variants = cfg.variants
    src: dict[str, list[str]] = {}
    for v in variants:
        d = variant_design(cfg, v)
        vdir = out / v.name
        src[v.name] = copy_sources(d, vdir / "rtl")
        fe = vdir / "frontend"
        fe.mkdir(parents=True, exist_ok=True)
        (fe / "frontend.ys").write_text(
            frontend_script(d, [f"../rtl/{f}" for f in src[v.name]], [c["module"] for c in cfg.cells]),
            encoding="utf-8")
    log(f"[1/3] reading the design ({len(variants)} variant(s))")
    executor.sync_up(out)
    cmd = " ; ".join(f"(cd {_q(out / v.name / 'frontend')} && yosys -q -l yosys.log frontend.ys "
                     f"> /dev/null 2>&1; echo $? > rc)" for v in variants)
    executor.run(cmd, out, timeout=600)
    executor.sync_down(out)
    netlists: dict[str, Netlist] = {}
    for v in variants:
        fe = out / v.name / "frontend"
        if not (fe / "netlist.json").exists():
            tail = (fe / "yosys.log").read_text(errors="replace")[-2000:] if (fe / "yosys.log").exists() else ""
            raise FlowError(f"variant '{v.name}': Yosys did not produce a netlist\n{tail}")
        netlists[v.name] = Netlist.load(fe / "netlist.json", cfg.design.top)
    return netlists


def _reuse_frontend(cfg: Config, reference: Path, out: Path, log=print) -> dict[str, Netlist]:
    """Reuse an identical frontend result without invoking Yosys again."""
    reference = reference.resolve()
    out = out.resolve()
    log(f"[1/3] reusing the design netlist ({len(cfg.variants)} variant(s))")
    netlists = {}
    for v in cfg.variants:
        d = variant_design(cfg, v)
        src = copy_sources(d, out / v.name / "rtl")
        fe = out / v.name / "frontend"
        fe.mkdir(parents=True, exist_ok=True)
        ref = reference / v.name / "frontend"
        expected = frontend_script(d, [f"../rtl/{f}" for f in src], [c["module"] for c in cfg.cells])
        (fe / "frontend.ys").write_text(expected, encoding="utf-8")
        if not (ref / "frontend.ys").exists() or (ref / "frontend.ys").read_text() != expected:
            raise FlowError(f"variant '{v.name}': reused netlist does not match the design")
        if ref.resolve() != fe.resolve():
            shutil.copy2(ref / "netlist.json", fe / "netlist.json")
        netlists[v.name] = Netlist.load(fe / "netlist.json", cfg.design.top)
    return netlists


def _run_after_frontend(cfg: Config, out: Path, executor: Executor, parallel: int,
                        only: list[str] | None, log, netlists: dict[str, Netlist],
                        cell_verdicts: dict[str, tuple[str, list[str]]] | None = None,
                        cell_results: dict[str, RunResult] | None = None) -> RunResult:
    out = out.resolve()
    variants = cfg.variants
    src = {v.name: _src_order(cfg, v) for v in variants}

    # 2. Structural analysis, then jobs: checks (with assumptions) and twins.
    structures, crossings_v, checks_v, assumptions_v = structural(cfg, out, variants, only)
    for v in variants:
        known = {c.name for c in checks_v[v.name]} | {x.name for x in crossings_v[v.name]} \
            | {a.name for a in assumptions_v[v.name]}
        for k in v.expect:
            if k not in known:
                log(f"warning: variant '{v.name}' expects '{k}', which is neither a check, "
                    f"an assumption nor a found crossing")
    jobs: list[tuple[str, Job]] = []
    environment: dict[str, set[str]] = {}
    for v in variants:
        d = variant_design(cfg, v)
        nl = netlists[v.name]
        checks = checks_v[v.name]
        assumptions = assumptions_v[v.name]
        env = [a for a in assumptions if is_environment(a, nl)]
        environment[v.name] = {a.name for a in env}
        jdir = out / v.name / "jobs"
        for c in checks:
            applied = [a for a in assumptions if a.applies_to is None or c.name in a.applies_to]
            jobs.append((v.name, build_job(variant_config(cfg, v), d, nl, c, src[v.name], jdir / c.name, "../../rtl",
                                           applied)))
            if variant_config(cfg, v).options.msi_ablate and c.params.get("msi"):
                baseline = dataclasses.replace(c, name=f"{c.name}_noms",
                                               params={**c.params, "msi": []}, expect=None)
                jobs.append((v.name, build_job(variant_config(cfg, v), d, nl, baseline, src[v.name],
                                               jdir / baseline.name, "../../rtl", applied, baseline_of=c.name)))
        for a in assumptions:
            if a.name in environment[v.name]:
                continue
            jobs.append((v.name, build_job(variant_config(cfg, v), d, nl, twin_check(a), src[v.name], jdir / a.name,
                                           "../../rtl", env, twin_of=a.name)))
    script = ["#!/usr/bin/env bash", "# Generated by open-formal-cdc: run all jobs", "cd \"$(dirname \"$0\")\"",
              "ls -d */jobs/*/ | xargs -P " + str(parallel) +
              " -I{} bash -c 'cd {} && rm -rf job_* && sby -f -j 2 job.sby > sby.log 2>&1; true'"]
    (out / "run_all.sh").write_text("\n".join(script) + "\n", encoding="utf-8")
    (out / "run_all.sh").chmod(0o755)
    log(f"[2/3] running SBY: {len(jobs)} job(s), {len(cfg.options.time_models)} time model(s)")
    t0 = time.time()
    if jobs:
        executor.sync_up(out)
        budget = cfg.options.timeout * 2 * max(1, len(jobs)) // max(1, parallel) + 600
        r = executor.run("./run_all.sh", out, timeout=budget)
        executor.sync_down(out)
        if r.returncode not in (0, 123):
            log(r.output[-2000:])

    # 3. Outcomes, assumption states, crossing verdicts.
    outcomes = []
    vexp = {v.name: v.expect for v in variants}
    for vname, job in jobs:
        res = job_results(job.dir, job.time_models)
        if job.check.template == "onechange":
            for m in res:
                if m.status == "cex" and m.trace:
                    why = explain_onechange(job.dir, job.check.name, m.trace, m.model)
                    if why:
                        m.detail = f"{m.detail}; change together: {why}"
        outcomes.append(CheckOutcome(vname, job.check.name, job.check.template, overall(res),
                                     vexp[vname].get(job.check.name), res,
                                     kind=("assumption" if job.twin_of else
                                           "msi_baseline" if job.baseline_of else "check"),
                                     assumes=job.assumes, baseline_of=job.baseline_of))
    verdicts: list[Verdict] = []
    states: dict[str, dict[str, str]] = {}
    for v in variants:
        mine = [o for o in outcomes if o.variant == v.name]
        twin_status = {o.check: o.status for o in mine if o.kind == "assumption"}
        twin_assumes = {o.check: o.assumes for o in mine if o.kind == "assumption"}
        check_status = {o.check: o.status for o in mine if o.kind == "check"}
        check_assumes = {o.check: o.assumes for o in mine if o.kind == "check"}
        st = assumption_states(assumptions_v[v.name], environment[v.name], twin_status)
        states[v.name] = st
        advisory = {c.name for c in checks_v[v.name] if c.params.get("role") == "convergence"}
        cell_of = {y.name: y.cell_type for y in (structures[v.name].crossings if v.name in structures else [])
                   if y.cell_type}
        for x in crossings_v[v.name]:
            verdict, reasons, deps = crossing_verdict(x, check_status, check_assumes, st, twin_assumes,
                                                      advisory)
            ct = cell_of.get(x.name)
            if ct and cell_verdicts and ct in cell_verdicts and x.scheme == "user_cell":
                cv, creasons = cell_verdicts[ct]
                verdict, reasons = (cv, creasons) if verdict in ("structural", "safe") else (verdict, reasons + creasons)
            verdicts.append(Verdict(v.name, x.name, x.scheme, verdict, reasons, deps,
                                    vexp[v.name].get(x.name)))
    log(f"[3/3] done in {time.time() - t0:.0f} s")
    result = RunResult(outcomes, verdicts, states, structures, crossings_v, assumptions_v, cell_results or {})
    write_json(cfg, result, out)
    return result


def write_json(cfg: Config, result: RunResult, out: Path) -> None:
    data = {
        "tool": "open-formal-cdc", "version": __version__, "config": str(cfg.path),
        "time_models": cfg.options.time_models,
        "results": [
            {"variant": o.variant, "check": o.check, "kind": o.kind, "template": o.template,
             "status": o.status, "expect": o.expect, "ok": o.ok, "assumes": o.assumes,
             "baseline_of": o.baseline_of, "models": [asdict(m) for m in o.models]}
            for o in result.outcomes
        ],
        "crossings": [{**asdict(v), "ok": v.ok} for v in result.verdicts],
        "cells": {name: {
            "results": [{"variant": o.variant, "check": o.check, "kind": o.kind, "template": o.template,
                         "status": o.status, "expect": o.expect, "ok": o.ok, "assumes": o.assumes,
                         "baseline_of": o.baseline_of, "models": [asdict(m) for m in o.models]}
                        for o in r.outcomes],
            "crossings": [{**asdict(v), "ok": v.ok} for v in r.verdicts],
        } for name, r in result.cell_results.items()},
    }
    (out / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    model = {"tool": "open-formal-cdc", "version": __version__, "schema": 1, "variants": {
        v.name: model_dict(cfg, v.name, result.outcomes,
                           [vd for vd in result.verdicts if vd.variant == v.name],
                           result.states.get(v.name, {}), result.crossings.get(v.name, cfg.crossings),
                           result.structures.get(v.name), result.assumptions.get(v.name, cfg.assumptions))
        for v in cfg.variants}}
    (out / "cdc_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")


def _src_order(cfg: Config, v) -> list[str]:
    """File names given to the sources by copy_sources (same order and renaming)."""
    names: list[str] = []
    for i, f in enumerate(variant_design(cfg, v).files):
        names.append(f.name if f.name not in names else f"{i}_{f.name}")
    return names


def structural(cfg: Config, out: Path, variants, only: list[str] | None = None):
    """Structural analysis per variant merged with the configuration: a configured
    crossing with the same (source, destination) replaces the found one; configured
    checks win over proposed checks with the same name."""
    structures: dict[str, Structure] = {}
    crossings_v: dict[str, list[Crossing]] = {}
    checks_v: dict[str, list[Check]] = {}
    assumptions_v: dict[str, list[Assumption]] = {}
    clock_names = {c.name for c in cfg.clocks}
    for v in variants:
        crossings = list(cfg.crossings)
        checks = list(cfg.checks)
        assumptions = list(cfg.assumptions)
        vcfg = variant_config(cfg, v)
        if vcfg.options.structural:
            data = json.loads((out / v.name / "frontend" / "netlist.json").read_text())
            st = analyze(Graph.from_json(data, cfg.design.top), cfg.clocks, cfg.inputs,
                         {r.port for r in cfg.resets}, cfg.clock_domains or None, cfg.outputs or None,
                         {c["module"]: cell_spec_from_config(c) for c in cfg.cells} or None)
            structures[v.name] = st
            (out / v.name / "structure.json").write_text(
                json.dumps(asdict(st), ensure_ascii=False, indent=2), encoding="utf-8")
            auto_x, auto_c, auto_a = to_config(st, clock_names, vcfg.options.pulse_checks,
                                               vcfg.options.pulse_min_edges, vcfg.options.meta_checks,
                                               vcfg.options.hazard_checks, vcfg.options.hazard_domain_inputs,
                                               vcfg.options.hazard_async, vcfg.options.rdc_checks,
                                               vcfg.options.clock_mux_checks, vcfg.options.m5_checks,
                                               vcfg.options.m5_group)
            anames = {a.name for a in assumptions}
            assumptions += [a for a in auto_a if a.name not in anames]
            have = {(x.src.signal, x.dst.signal) for x in crossings}
            crossings += [x for x in auto_x if (x.src.signal, x.dst.signal) not in have]
            names = {c.name for c in checks}
            checks += [c for c in auto_c if c.name not in names]
        if only:
            checks = [c for c in checks if c.name in only]
        crossings_v[v.name] = crossings
        checks_v[v.name] = checks
        assumptions_v[v.name] = assumptions
    return structures, crossings_v, checks_v, assumptions_v
