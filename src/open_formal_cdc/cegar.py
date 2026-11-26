# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Counterexample-guided refinement of explicit netlist cuts.

Every final verdict comes from the full model. Abstract counterexamples are marked
confirmed or discharged; abstract covers are never treated as concrete witnesses.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import Check, Config
from .executor import Executor
from .flow import FlowError, RunResult, frontend, run
from .focus import propose_cuts
from .results import parse_task
from .structural import Graph
from .trace_refine import prioritize


@dataclass
class Round:
    name: str
    cuts: list[str]
    status: str
    models: dict[str, str]
    path: str
    trace: str | None = None
    removed: str | None = None
    proof: dict[str, str] = field(default_factory=dict)


@dataclass
class CaseResult:
    variant: str
    check: str
    status: str                    # proven | cex | unknown | error
    abstract_cex: str              # none | confirmed | discharged | unresolved
    full_status: str
    detail: str
    cut_evidence: dict[str, str] = field(default_factory=dict)
    rounds: list[Round] = field(default_factory=list)


def _check(cfg: Config, name: str) -> Check:
    check = next((c for c in cfg.checks if c.name == name), None)
    if check is None:
        raise FlowError(f"cegar: check '{name}' must be declared explicitly in the configuration")
    return check


def _with_cuts(cfg: Config, name: str, cuts: list[str]) -> Config:
    out = copy.copy(cfg)
    out.checks = [dataclasses.replace(c, params={**c.params, "cut": list(cuts)})
                  if c.name == name else c for c in cfg.checks]
    return out


def _outcome(result: RunResult, name: str):
    matches = [o for o in result.outcomes if o.kind == "check" and o.check == name]
    if len(matches) != 1:
        raise FlowError(f"cegar: expected one outcome for '{name}', got {len(matches)}")
    return matches[0]


def _has_cex(result: RunResult, name: str) -> bool:
    return any(m.status == "cex" for m in _outcome(result, name).models)


def _proof_passed(out: Path, result: RunResult, name: str) -> bool:
    outcome = _outcome(result, name)
    return bool(outcome.models) and all(
        parse_task(out / outcome.variant / "jobs" / name / f"job_{m.model}_prove").status == "PASS"
        for m in outcome.models)


def _trace(result: RunResult, name: str) -> str | None:
    return next((m.trace for m in _outcome(result, name).models if m.trace), None)


def _round(name: str, cuts: list[str], result: RunResult, check: str, out: Path,
           removed: str | None = None) -> Round:
    outcome = _outcome(result, check)
    proof = {m.model: parse_task(out / outcome.variant / "jobs" / check / f"job_{m.model}_prove").status
             for m in outcome.models}
    return Round(name, list(cuts), outcome.status, {m.model: m.status for m in outcome.models}, str(out),
                 _trace(result, check), removed, proof)


def _prioritized(result: RunResult, name: str, cuts: list[str], variant: str, log) -> list[str]:
    trace = _trace(result, name)
    if not trace:
        return cuts
    ordered = prioritize(trace, cuts)
    if ordered != cuts:
        log(f"[cegar] {variant}/{name}: trace activity orders cuts as {', '.join(ordered)}")
    return ordered


def _final_status(out: Path, result: RunResult, name: str, abstract_cex: bool,
                  abstract_proof: bool) -> tuple[str, str, str, str]:
    outcome = _outcome(result, name)
    concrete_cex = _has_cex(result, name)
    concrete_proof = _proof_passed(out, result, name)
    if abstract_proof and concrete_cex:
        return "error", "unresolved", outcome.status, "full model contradicts the abstract proof"
    if concrete_cex:
        return "cex", "confirmed" if abstract_cex else "none", outcome.status, \
            "counterexample confirmed on the full model"
    if all(m.status == "proven" for m in outcome.models):
        discharged = abstract_cex and concrete_proof
        return "proven", "discharged" if discharged else "none", outcome.status, \
            "full proof and covers passed"
    if abstract_cex and concrete_proof:
        return "unknown", "discharged", outcome.status, \
            "abstract counterexample discharged by the full proof; full covers are unresolved"
    if abstract_proof:
        return "unknown", "none", outcome.status, \
            "proof holds on the abstraction; full covers are unresolved"
    return "unknown", "unresolved" if abstract_cex else "none", outcome.status, \
        "no definitive full-model result"


def cegar(cfg: Config, out: Path, executor: Executor, parallel: int = 8,
          only: list[str] | None = None, max_rounds: int = 6, log=print) -> list[CaseResult]:
    """Refine explicit cuts or an automatic en_stable/gray focus and write cegar.json."""
    if only is None or len(only) != 1:
        raise FlowError("cegar: select exactly one check with --check")
    name = only[0]
    check = _check(cfg, name)
    configured_cuts = [str(n) for n in check.params.get("cut") or []]
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in cfg.variants:
        case_cfg = copy.copy(cfg)
        case_cfg.variants = [variant]
        case_out = out / variant.name
        current = list(configured_cuts)
        if not current and check.template not in ("en_stable", "gray"):
            raise FlowError(f"cegar: check '{name}' needs explicit cuts; "
                            "automatic focus supports en_stable and gray")
        base_dir = case_out / "frontend_base"
        frontend(case_cfg, base_dir, executor, log)
        if not current:
            netlist = json.loads((base_dir / variant.name / "frontend" / "netlist.json").read_text())
            graph = Graph.from_json(netlist, case_cfg.design.top)
            current = propose_cuts(graph, check.template, check.params)
            if not current:
                raise FlowError(f"cegar: no enable-boundary cuts found for '{name}'; specify 'cut' explicitly")
            case_cfg.checks = [dataclasses.replace(c, params={**c.params, "cut_mode": "state"})
                               if c.name == name else c for c in case_cfg.checks]
            (case_out / "focus.json").write_text(json.dumps(
                {"rule": f"{check.template} sequential boundary", "cut_mode": "state", "cuts": current}, indent=2) + "\n",
                encoding="utf-8")
        log(f"[cegar] {variant.name}/{name}: {len(current)} initial cut(s)")
        rounds: list[Round] = []
        evidence = {cut: "untested" for cut in current}
        abstract_dir = case_out / "abstract"
        abstract = run(_with_cuts(case_cfg, name, current), abstract_dir, executor,
                       parallel, [name], log, reuse_from=base_dir)
        rounds.append(_round("abstract", current, abstract, name, abstract_dir))
        abstract_cex = _has_cex(abstract, name)
        abstract_proof = _proof_passed(abstract_dir, abstract, name)
        full = None
        full_dir = None
        if abstract_cex:
            current = _prioritized(abstract, name, current, variant.name, log)
            index = 0
            attempts = 0
            while index < len(current) and attempts < max_rounds:
                removed = current[index]
                candidate = current[:index] + current[index + 1:]
                attempts += 1
                round_name = f"refine_{attempts}_without_{len(rounds)}"
                round_dir = case_out / f"refine_{attempts}"
                refined = run(_with_cuts(case_cfg, name, candidate), round_dir, executor,
                              parallel, [name], log, reuse_from=base_dir)
                rounds.append(_round(round_name, candidate, refined, name, round_dir, removed))
                if _has_cex(refined, name):
                    evidence[removed] = "not_required"
                elif _proof_passed(round_dir, refined, name):
                    evidence[removed] = "discharges"
                else:
                    evidence[removed] = "inconclusive"
                if _has_cex(refined, name):
                    current = _prioritized(refined, name, candidate, variant.name, log)
                    index = 0
                    log(f"[cegar] {variant.name}/{name}: counterexample remains without {removed}")
                else:
                    index += 1
                    log(f"[cegar] {variant.name}/{name}: restore {removed} ({evidence[removed]})")
                if not candidate:
                    full, full_dir = refined, round_dir
                    break
        if full is None:
            full_dir = case_out / "full"
            full = run(_with_cuts(case_cfg, name, []), full_dir, executor,
                       parallel, [name], log, reuse_from=base_dir)
            rounds.append(_round("full", [], full, name, full_dir))
        status, cex_state, full_status, detail = _final_status(
            full_dir, full, name, abstract_cex, abstract_proof)
        results.append(CaseResult(variant.name, name, status, cex_state, full_status, detail, evidence, rounds))
        log(f"[cegar] {variant.name}/{name}: {status}; abstract_cex={cex_state}")
    (out / "cegar.json").write_text(json.dumps([asdict(r) for r in results], indent=2) + "\n",
                                    encoding="utf-8")
    return results
