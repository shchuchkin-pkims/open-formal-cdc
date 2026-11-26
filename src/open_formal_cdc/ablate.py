# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Ablation of environment assumptions: prove with all, then once without each."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Config
from .executor import Executor
from .flow import RunResult, run


@dataclass
class Effect:
    assumption: str
    classification: str
    baseline: dict[str, str]
    without: dict[str, str]


def _statuses(result: RunResult) -> dict[str, str]:
    return {f"{o.variant}/{o.check}": o.status for o in result.outcomes}


def _verdicts(result: RunResult) -> dict[str, str]:
    return {f"{v.variant}/{v.crossing}": v.verdict for v in result.verdicts}


def ablate(cfg: Config, out: Path, executor: Executor, parallel: int = 8,
           only: list[str] | None = None, log=print) -> list[Effect]:
    out = out.resolve()
    baseline = run(cfg, out / "with_all", executor, parallel, only, log)
    base = _statuses(baseline)
    base_verdicts = _verdicts(baseline)
    effects = []
    for assumption in cfg.assumptions:
        reduced = copy.copy(cfg)
        reduced.assumptions = [a for a in cfg.assumptions if a.name != assumption.name]
        without_result = run(reduced, out / f"without_{assumption.name}", executor, parallel, only, log)
        without = _statuses(without_result)
        without_verdicts = _verdicts(without_result)
        if any(base.get(k) == "proven" and without.get(k) == "cex" for k in base):
            classification = "helps"
        elif base == without and base_verdicts == without_verdicts:
            classification = "redundant"
        else:
            classification = "changes"
        effects.append(Effect(assumption.name, classification, base, without))
    payload = [asdict(e) for e in effects]
    (out / "ablation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return effects
