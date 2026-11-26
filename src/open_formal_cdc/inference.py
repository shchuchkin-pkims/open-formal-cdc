# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""End-to-end extraction and formal filtering of environment assumptions."""

from __future__ import annotations

import copy
import dataclasses
import json
import re
import shlex
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from .config import (Assumption, Check, Config, Design, Input, Variant, variant_config,
                     variant_design)
from .executor import Executor
from .flow import FlowError, frontend, run, structural
from .frontend import copy_sources
from .infer import (Candidate, FormalAnswer, blocking_steps, design_signals, formal_filters,
                    mine, sample_trace)
from .jobs import Job, build_job, twin_check, vid
from .netlist import Netlist
from .results import parse_task


def _outcome(result, name):
    matches = [o for o in result.outcomes if o.kind == "check" and o.check == name]
    if len(matches) != 1:
        raise FlowError(f"infer: expected one outcome for '{name}', got {len(matches)}")
    return matches[0]


def _vacuity_spec(check: Check) -> list[dict[str, str]]:
    p = check.params
    if check.template == "en_stable":
        names = [p.get("data"), p.get("enable")]
    elif check.template == "gray":
        names = [p.get("signal")]
    elif check.template == "hs_req":
        names = [p.get("req"), p.get("ack")]
    else:
        raise FlowError(f"infer: template '{check.template}' has no vacuity description; "
                        "supported templates: en_stable, gray, hs_req")
    if not p.get("clock") or not all(names):
        raise FlowError(f"infer: check '{check.name}' lacks its clock or assertion signals")
    return [{"signal": str(n), "clock": str(p["clock"])} for n in names]


def _execute(job: Job, executor: Executor, timeout: int) -> Job:
    root = job.dir.parents[1]
    relative = job.dir.relative_to(root)
    command = (f"cd {shlex.quote(str(relative))} && rm -rf job_* && "
               "sby -f -j 2 job.sby > sby.log 2>&1")
    executor.sync_up(root)
    try:
        executor.run(command, root, timeout=timeout)
    finally:
        executor.sync_down(root)
    return job


def _assumption_nets(a: Assumption) -> set[str]:
    p = a.params
    nets = {str(n) for n in p.get("signals") or []}
    for key in ("signal", "allow", "select_d", "select", "on"):
        if p.get(key):
            nets.add(str(p[key]))
    if a.kind == "protocol":
        nets |= {str(x["signal"]) for x in p.get("antecedent") or []}
        nets.add(str(p["consequent"]["signal"]))
    if a.kind == "trace_block":
        nets |= {str(n) for step in p.get("steps") or [] for n in step}
    return nets


def _base_net(name: str) -> str:
    return re.sub(r"\[\d+(?::\d+)?\]$", "", name)


class _VariantInference:
    def __init__(self, cfg: Config, variant: Variant, check: Check, assumptions: list[Assumption],
                 base_dir: Path, root: Path, executor: Executor, baseline_depth: dict[str, int],
                 parallel: int = 8, log=print):
        self.cfg = cfg
        self.variant = variant
        self.check = check
        self.assumptions = [a for a in assumptions
                            if a.applies_to is None or check.name in a.applies_to]
        self.base_dir = base_dir
        self.root = root
        self.executor = executor
        self.baseline_depth = baseline_depth
        self.parallel = parallel
        self.log = log
        self.nl = Netlist.load(base_dir / variant.name / "frontend" / "netlist.json", cfg.design.top)
        self.vcfg = variant_config(cfg, variant)
        self.actual: dict[Candidate, Job] = {}
        self.free_supported = True
        self.free_cfg, self.free_nl, self.free_root, self.free_assumptions = self._free_model()

    def _free_model(self):
        root = self.root / "free"
        rtl = root / "rtl"
        rtl.mkdir(parents=True, exist_ok=True)
        path = rtl / "free.sv"
        clocks = {c.port for c in self.cfg.clocks}
        resets = {r.port for r in self.cfg.resets}
        ports = [p for p in self.nl.ports.values() if p.name not in resets]
        declarations = [f"input {'[' + str(p.width - 1) + ':0] ' if p.width > 1 else ''}{vid(p.name)}"
                        for p in ports]
        path.write_text(f"module ofcdc_free (\n  " + ",\n  ".join(declarations) + "\n);\nendmodule\n",
                        encoding="utf-8")
        data = {"modules": {"ofcdc_free": {
            "ports": {p.name: {"direction": "input", "bits": list(range(p.width))} for p in ports},
            "netnames": {p.name: {"bits": list(range(p.width))} for p in ports}}}}
        nl = Netlist(data, "ofcdc_free")
        clock_of = {}
        for signal in design_signals(self.cfg, self.nl, include_async=True):
            if signal.clock:
                clock_of.setdefault(_base_net(signal.name), signal.clock)
        inputs = [Input(p.name, clock_of.get(p.name)) for p in ports if p.name not in clocks]
        options = dataclasses.replace(self.vcfg.options, structural=False)
        design = Design("ofcdc_free", [path])
        cfg = Config(self.cfg.path, design, list(self.cfg.clocks), [], inputs, [], options,
                     [Variant("base", {}, {})])
        supported = []
        for assumption in self.assumptions:
            nets = _assumption_nets(assumption)
            if assumption.params.get("signals_match"):
                self.free_supported = False
            if any(_base_net(n) not in nl.nets for n in nets):
                self.free_supported = False
            else:
                supported.append(assumption)
        self.free_supported &= len(supported) == len(self.assumptions)
        return cfg, nl, root, supported

    def _free_job(self, candidate: Candidate, stage: str) -> Job:
        clock = str(self.check.params["clock"])
        assumption = Assumption("candidate", "protocol", candidate.params(clock))
        if stage == "triviality":
            check = twin_check(assumption)
            assumptions = self.free_assumptions
        else:
            depth = max(4, self.vcfg.options.reset_steps + 4)
            check = Check("consistency", "horizon", {"depth": depth})
            assumptions = self.free_assumptions + [assumption]
        cfg = copy.copy(self.free_cfg)
        cfg.options = dataclasses.replace(cfg.options, cover_depth=check.params.get("depth", cfg.options.cover_depth))
        root = self.free_root / f"{stage}_{self._index(candidate)}"
        (root / "rtl").mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.free_root / "rtl" / "free.sv", root / "rtl" / "free.sv")
        job_dir = root / "jobs" / stage
        job = build_job(cfg, cfg.design, self.free_nl, check, ["free.sv"], job_dir, "../../rtl", assumptions)
        return _execute(job, self.executor, cfg.options.timeout * 2 * max(1, len(cfg.options.time_models)) + 120)

    def _index(self, candidate: Candidate) -> str:
        import hashlib
        return hashlib.sha1(str(candidate).encode()).hexdigest()[:12]

    def _actual_job(self, candidate: Candidate) -> Job:
        clock = str(self.check.params["clock"])
        assumption = Assumption("candidate", "protocol", candidate.params(clock))
        check = dataclasses.replace(self.check, params={**self.check.params,
                                                        "vacuity": _vacuity_spec(self.check)})
        root = self.root / "actual" / self._index(candidate)
        design = variant_design(self.cfg, self.variant)
        sources = copy_sources(design, root / "rtl")
        job_dir = root / "jobs" / self._index(candidate)
        job = build_job(self.vcfg, design, self.nl, check, sources, job_dir, "../../rtl",
                        self.assumptions + [assumption])
        return _execute(job, self.executor, self.vcfg.options.timeout * 2 *
                        max(1, len(self.vcfg.options.time_models)) + 120)

    @staticmethod
    def _proof(job: Job) -> str:
        statuses = [parse_task(job.dir / f"job_{model}_prove").status for model in job.time_models]
        if all(s == "PASS" for s in statuses):
            return "proven"
        if all(s == "FAIL" for s in statuses):
            return "cex"
        if any(s == "FAIL" for s in statuses):
            return "model_mismatch"
        return "unknown"

    @staticmethod
    def _details(job: Job) -> str:
        return ", ".join(f"{model}: prove={parse_task(job.dir / f'job_{model}_prove').status}, "
                         f"cover={parse_task(job.dir / f'job_{model}_cover').status}"
                         for model in job.time_models)

    def evaluate_many(self, candidates: list[Candidate], stage: str) -> dict[Candidate, FormalAnswer]:
        if not candidates:
            return {}
        self.log(f"[infer] {self.variant.name}/{self.check.name}: {stage}, "
                 f"{len(candidates)} independent job(s)")
        with ThreadPoolExecutor(max_workers=min(self.parallel, len(candidates))) as pool:
            jobs = {candidate: pool.submit(self.evaluate, candidate, stage) for candidate in candidates}
            out = {}
            for candidate, future in jobs.items():
                try:
                    out[candidate] = future.result()
                except Exception as e:
                    out[candidate] = FormalAnswer("unknown", detail=str(e))
            return out

    def evaluate(self, candidate: Candidate, stage: str) -> FormalAnswer:
        if stage in ("triviality", "consistency") and not self.free_supported:
            return FormalAnswer("unknown", detail="user assumption is not on top-level I/O")
        if stage == "triviality":
            job = self._free_job(candidate, stage)
            proof = self._proof(job)
            value = "trivial" if proof == "proven" else "nontrivial" if proof == "cex" else "unknown"
            return FormalAnswer(value, detail=self._details(job))
        if stage == "consistency":
            job = self._free_job(candidate, stage)
            covers = [parse_task(job.dir / f"job_{m}_cover").status for m in job.time_models]
            value = ("consistent" if all(s == "PASS" for s in covers) else
                     "inconsistent" if all(s == "FAIL" for s in covers) else "unknown")
            return FormalAnswer(value, detail=self._details(job))
        if candidate not in self.actual:
            self.actual[candidate] = self._actual_job(candidate)
        job = self.actual[candidate]
        proof = self._proof(job)
        if stage == "vacuity":
            if proof in ("cex", "model_mismatch"):
                return FormalAnswer("nonvacuous", detail=self._details(job))
            if proof != "proven":
                return FormalAnswer("unknown", detail=self._details(job))
            tasks = [parse_task(job.dir / f"job_{m}_prove") for m in job.time_models]
            if any(t.unreached for t in tasks):
                return FormalAnswer("vacuous", detail=self._details(job))
            covers = [parse_task(job.dir / f"job_{m}_cover").status for m in job.time_models]
            return FormalAnswer("nonvacuous" if all(s == "PASS" for s in covers) else "unknown",
                                detail=self._details(job))
        if proof == "proven":
            covers = [parse_task(job.dir / f"job_{m}_cover").status for m in job.time_models]
            return FormalAnswer("proven" if all(s == "PASS" for s in covers) else "unknown",
                                quality=1.0 if all(s == "PASS" for s in covers) else None,
                                detail=self._details(job))
        if proof != "cex":
            return FormalAnswer("unknown", detail=self._details(job))
        quality = []
        for model in job.time_models:
            task = parse_task(job.dir / f"job_{model}_prove")
            if not task.failed or model not in self.baseline_depth:
                return FormalAnswer("unknown", detail=self._details(job))
            new = task.failed[0][1]
            old = self.baseline_depth[model]
            quality.append(max(0.0, (new - old) / new) if new else 0.0)
        return FormalAnswer("cex", quality=min(quality), detail=self._details(job))


def _candidate_dict(result) -> dict:
    return {"expression": str(result.candidate), "status": result.status, "reason": result.reason,
            "quality": result.quality, "filters": result.filters, "implied_by": result.implied_by,
            "details": result.details, "params": result.candidate.params("")}


def infer(cfg: Config, out: Path, executor: Executor, parallel: int = 8,
          only: list[str] | None = None, max_limit: int = 10, common_threshold: float = 1.0,
          log=print) -> list[dict]:
    if only is None or len(only) != 1:
        raise FlowError("infer: select exactly one check with --check")
    if max_limit < 1:
        raise FlowError("infer: max_limit must be positive")
    name = only[0]
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for variant in cfg.variants:
        case_cfg = copy.copy(cfg)
        case_cfg.variants = [variant]
        case_cfg.cells = []
        base_dir = out / variant.name / "frontend_base"
        frontend(case_cfg, base_dir, executor, log)
        _, _, checks, assumptions = structural(case_cfg, base_dir, [variant], [name])
        if len(checks[variant.name]) != 1:
            raise FlowError(f"infer: check '{name}' not found in variant '{variant.name}'")
        check = checks[variant.name][0]
        clock = str(check.params.get("clock", ""))
        _vacuity_spec(check)
        nl = Netlist.load(base_dir / variant.name / "frontend" / "netlist.json", cfg.design.top)
        signals = [s for s in design_signals(case_cfg, nl) if s.clock == clock]
        if not any(s.direction == "input" for s in signals):
            raise FlowError(f"infer: no top-level inputs in clock domain '{clock}'")
        block_signals = design_signals(case_cfg, nl, include_async=True)
        case_cfg.options = dataclasses.replace(case_cfg.options, structural=False)
        case_cfg.variants = [dataclasses.replace(variant, expect={},
                                                 options={**variant.options, "structural": False})]
        case_cfg.checks = [check]
        case_cfg.crossings = []
        case_cfg.assumptions = list(assumptions[variant.name])
        base_assumptions = list(case_cfg.assumptions)
        blocks = []
        seen = set()
        trace_paths = []
        baseline_depth = {}
        stop_reason = "no more counterexamples"
        for iteration in range(max_limit):
            current = copy.copy(case_cfg)
            current.assumptions = base_assumptions + blocks
            result = run(current, out / variant.name / f"counterexamples_{iteration}", executor,
                         parallel, [name], log, reuse_from=base_dir)
            cex = [m for m in _outcome(result, name).models if m.status == "cex" and m.trace]
            added = False
            for model in cex:
                if model.step is not None:
                    baseline_depth.setdefault(model.model, model.step)
                steps = blocking_steps(model.trace, block_signals)
                signature = json.dumps(steps, sort_keys=True)
                if not steps or signature in seen:
                    continue
                seen.add(signature)
                trace_paths.append(model.trace)
                blocks.append(Assumption(f"inferred_block_{len(blocks)}", "trace_block",
                                         {"steps": steps, "verify": False}))
                added = True
                if len(trace_paths) >= max_limit:
                    break
            if not added:
                stop_reason = "counterexamples have no new top-level input sequence"
                break
            if len(trace_paths) >= max_limit:
                stop_reason = "counterexample limit reached"
                break
        rows = [sample_trace(path, signals, clock) for path in trace_paths]
        rows = [row for row in rows if row]
        mined = mine(rows, signals, common_threshold) if rows else mine([], signals)
        engine = _VariantInference(case_cfg, case_cfg.variants[0], check, base_assumptions,
                                   base_dir, out / variant.name / "filters", executor, baseline_depth,
                                   parallel, log)
        evaluated = formal_filters(mined, engine.evaluate, engine.evaluate_many) if mined.candidates else []
        report = {"variant": variant.name, "check": name, "clock": clock, "traces": trace_paths,
                  "stop_reason": stop_reason, "mined": mined.mined,
                  "syntactic_rejected": {k: len(v) for k, v in mined.rejected.items()},
                  "implications": {str(k): [str(x) for x in v] for k, v in mined.implications.items()},
                  "candidates": [_candidate_dict(r) for r in evaluated]}
        for candidate in report["candidates"]:
            candidate["params"]["clock"] = clock
        reports.append(report)
        log(f"[infer] {variant.name}/{name}: {len(trace_paths)} traces, {mined.mined} mined, "
            f"{len(evaluated)} after syntactic filters")
    (out / "assumptions.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    accepted = []
    index = 0
    for report in reports:
        candidates = [c for c in report["candidates"] if c["status"] == "candidate" and c["quality"]]
        candidates.sort(key=lambda c: -c["quality"])
        for candidate in candidates:
            accepted.append({"name": f"inferred_{index:04d}", "kind": "protocol",
                             **candidate["params"], "expression": candidate["expression"],
                             "quality": candidate["quality"], "implied_by": candidate["implied_by"]})
            index += 1
    (out / "assumptions.yaml").write_text(yaml.safe_dump({"assumptions": accepted}, sort_keys=False),
                                         encoding="utf-8")
    return reports
