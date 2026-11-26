# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Parsing SBY results and deriving the check outcome.

Outcome of a check in one time model (policy from docs/architecture.md, 4.10):
- proven  - the proof passed and all covers were reached;
- cex     - counterexample (an assertion failed);
- vacuous - the proof passed and some covers were independently proven unreachable;
- unknown - limit reached, a bounded cover search failed, or the engine gave no answer;
- error   - build or engine error.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_FAILED = re.compile(r"failed assertion (\S+) at (\S+) step (\d+)")
_REACHED = re.compile(r"reached cover statement (\S+) at (\S+) step (\d+)")
_UNREACHED = re.compile(r"unreached cover statement (\S+)")
_TRACE = re.compile(r"(?:counterexample|cover) trace: (\S+)")
_ELAPSED = re.compile(r"Elapsed clock time \[H:MM:SS \(secs\)\]: \S+ \((\d+)\)")
_ERROR = re.compile(r"ERROR: (.*)")
_ENGINE_FAIL = re.compile(r"summary: engine_\d+ \([^)]*\) returned FAIL")


def _unreached_summary(log: str) -> list[str]:
    names = []
    listed = False
    for line in log.splitlines():
        if "summary: unreached cover statements:" in line:
            listed = True
            continue
        if not listed:
            continue
        m = re.search(r"summary:\s+(\S+) at ", line)
        if m is None:
            listed = False
        else:
            names.append(m.group(1))
    return names


@dataclass
class TaskResult:
    status: str                    # PASS | FAIL | UNKNOWN | TIMEOUT | ERROR | MISSING
    failed: list[tuple[str, int]] = field(default_factory=list)
    reached: list[tuple[str, int]] = field(default_factory=list)
    unreached: list[str] = field(default_factory=list)
    traces: list[str] = field(default_factory=list)
    seconds: int = 0
    error: str = ""


@dataclass
class ModelResult:
    model: str
    status: str                    # proven | cex | vacuous | unknown | error
    step: int | None = None        # counterexample depth
    trace: str | None = None
    detail: str = ""
    seconds: int = 0


def parse_task(task_dir: Path) -> TaskResult:
    status_file = task_dir / "status"
    log_file = task_dir / "logfile.txt"
    if not status_file.exists():
        err = ""
        if log_file.exists():
            m = _ERROR.findall(log_file.read_text(errors="replace"))
            err = m[-1] if m else ""
        return TaskResult("ERROR" if err else "MISSING", error=err)
    status = status_file.read_text().split()[0] if status_file.read_text().split() else "ERROR"
    log = log_file.read_text(errors="replace") if log_file.exists() else ""
    r = TaskResult(status)
    r.failed = [(n, int(s)) for n, _, s in _FAILED.findall(log)]
    r.reached = [(n, int(s)) for n, _, s in _REACHED.findall(log)]
    r.unreached = sorted(set(_UNREACHED.findall(log)) | set(_unreached_summary(log)))
    r.traces = [str((task_dir.parent / t).resolve()) if not Path(t).is_absolute() else t
                for t in _TRACE.findall(log)]
    m = _ELAPSED.findall(log)
    r.seconds = int(m[-1]) if m else 0
    errs = _ERROR.findall(log)
    r.error = errs[-1] if errs else ""
    if r.status == "ERROR" and _ENGINE_FAIL.search(log):
        # the engine found a counterexample but the trace could not be replayed
        r.status = "FAIL"
        r.error = "counterexample without trace: " + r.error
    return r


def combine(model: str, prove: TaskResult, cover: TaskResult) -> ModelResult:
    t = prove.seconds + cover.seconds
    if prove.status == "FAIL":
        step = prove.failed[0][1] if prove.failed else None
        name = prove.failed[0][0] if prove.failed else ""
        return ModelResult(model, "cex", step, prove.traces[0] if prove.traces else None,
                           f"failed {name}" if name else (prove.error or "failed"), t)
    if prove.status in ("ERROR", "MISSING") or cover.status in ("ERROR", "MISSING"):
        msg = prove.error or cover.error or "no result"
        return ModelResult(model, "error", detail=msg, seconds=t)
    if prove.status == "PASS":
        if cover.status == "PASS":
            return ModelResult(model, "proven", seconds=t)
        detail = f"cover: {cover.status}"
        if cover.unreached:
            detail += "; bounded search did not reach: " + ", ".join(cover.unreached)
        return ModelResult(model, "unknown", detail=detail, seconds=t)
    return ModelResult(model, "unknown", detail=f"prove: {prove.status}", seconds=t)


def job_results(job_dir: Path, models: list[str]) -> list[ModelResult]:
    out = []
    for m in models:
        prove = parse_task(job_dir / f"job_{m}_prove")
        cover = parse_task(job_dir / f"job_{m}_cover")
        out.append(combine(m, prove, cover))
    return out


def overall(results: list[ModelResult]) -> str:
    """Outcome over all time models; disagreement is a separate outcome."""
    statuses = {r.status for r in results}
    if len(statuses) == 1:
        return statuses.pop()
    return "model_mismatch"


def to_dict(r: ModelResult) -> dict:
    return asdict(r)
