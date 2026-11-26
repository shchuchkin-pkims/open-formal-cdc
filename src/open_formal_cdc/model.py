# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Design model (cdc_model.json) and verdicts per crossing.

Assumption states:
- environment - constrains only top-level inputs; cannot be verified on the design;
- proven      - its twin job proved it (under environment assumptions only);
- refuted     - its twin job found a counterexample;
- unverified  - the twin job gave no definite answer.

Crossing verdicts (docs/architecture.md, 4.10):
- safe          - all checks proven, all assumptions it relies on proven;
- safe_assuming - as safe, but relies on environment assumptions;
- unsafe        - a check found a counterexample;
- no_scheme     - no synchronization scheme;
- structural    - scheme recognized, no formal checks for it (yet);
- unresolved    - anything else; reasons are listed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import Config, Crossing

# Schemes that are acceptable by structure alone when no checks are attached.
STRUCTURAL_SCHEMES = ("ndff", "reset_sync", "user_cell", "async_fifo")


@dataclass
class Verdict:
    variant: str
    crossing: str
    scheme: str
    verdict: str
    reasons: list[str] = field(default_factory=list)
    relies_on: list[str] = field(default_factory=list)
    expect: str | None = None

    @property
    def ok(self) -> bool | None:
        return None if self.expect is None else self.verdict == self.expect


def assumption_states(assumptions: list, environment: set[str], twin_status: dict[str, str]) -> dict[str, str]:
    states = {}
    for a in assumptions:
        if a.name in environment:
            states[a.name] = "environment"
        else:
            st = twin_status.get(a.name)
            states[a.name] = {"proven": "proven", "cex": "refuted"}.get(st, "unverified")
    return states


def crossing_verdict(x: Crossing, check_status: dict[str, str], check_assumes: dict[str, list[str]],
                     states: dict[str, str], twin_assumes: dict[str, list[str]],
                     advisory: set[str] | None = None) -> tuple[str, list[str], list[str]]:
    """Verdict, reasons and the closure of assumptions the crossing relies on."""
    deps: list[str] = []

    def add(name: str) -> None:
        if name not in deps:
            deps.append(name)
            for d in twin_assumes.get(name, []):
                add(d)

    for a in x.assumptions:
        add(a)
    for c in x.checks:
        for a in check_assumes.get(c, []):
            add(a)

    if x.structural_error:
        return "unsafe", [x.structural_error], deps
    if x.structural_warning:
        return "warning", [x.structural_warning], deps
    if x.structural_note:
        return "note", [x.structural_note], deps
    if x.scheme == "none":
        return "no_scheme", ["no synchronization scheme"], deps
    advisory = advisory or set()
    cex = [c for c in x.checks if check_status.get(c) == "cex" and c not in advisory]
    if cex:
        return "unsafe", [f"counterexample in {c}" for c in cex], deps
    reasons = []
    for c in x.checks:
        st = check_status.get(c, "not run")
        if st == "cex" and c in advisory:
            reasons.append(f"convergence: the sources may change in one step ({c}); review")
        elif st != "proven":
            reasons.append(f"check {c}: {st}")
    for a in deps:
        if states.get(a) == "refuted":
            reasons.append(f"assumption {a} refuted")
        elif states.get(a) == "unverified":
            reasons.append(f"assumption {a} not verified")
    if reasons:
        return "unresolved", reasons, deps
    if not x.checks and not x.assumptions:
        if x.scheme in STRUCTURAL_SCHEMES:
            return "structural", [f"scheme {x.scheme} accepted by structure"], deps
        return "unresolved", [f"no checks for scheme {x.scheme}"], deps
    env = [a for a in deps if states.get(a) == "environment"]
    if env:
        return "safe_assuming", [f"environment assumption {a}" for a in env], deps
    return "safe", [], deps


def model_dict(cfg: Config, variant: str, outcomes: list, verdicts: list[Verdict],
               states: dict[str, str], crossings: list[Crossing], structure=None,
               assumptions: list | None = None) -> dict:
    """One variant of the design model."""
    sx = {x.name: x for x in structure.crossings} if structure else {}
    return {
        "design": {"top": cfg.design.top, "files": [str(f) for f in cfg.design.files]},
        "clocks": [asdict(c) for c in cfg.clocks],
        "resets": [asdict(r) for r in cfg.resets],
        "inputs": [asdict(i) for i in cfg.inputs],
        "assumptions": [{"name": a.name, "kind": a.kind, "params": a.params,
                         "applies_to": a.applies_to, "state": states.get(a.name)}
                        for a in (cfg.assumptions if assumptions is None else assumptions)],
        "crossings": [{"name": x.name, "from": asdict(x.src), "to": asdict(x.dst),
                       "scheme": x.scheme, "checks": x.checks, "assumptions": x.assumptions,
                       "structure": {k: v for k, v in asdict(sx[x.name]).items()
                                     if k in ("stages", "enable", "enable_active", "logic", "bits", "notes")}
                       if x.name in sx else None,
                       **{k: v for k, v in asdict(vd).items() if k in ("verdict", "reasons", "relies_on")}}
                      for x in crossings for vd in verdicts if vd.crossing == x.name],
        "convergence": structure.convergence if structure else [],
        "warnings": structure.warnings if structure else [],
        "divergence": structure.divergence if structure else [],
        "checks": [{"name": o.check, "kind": o.kind, "template": o.template, "status": o.status,
                    "assumes": o.assumes, "models": [asdict(m) for m in o.models]}
                   for o in outcomes if o.variant == variant],
    }
