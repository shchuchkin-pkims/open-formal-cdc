# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Mine protocol assumptions from counterexamples (Plassan, chapter 5)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from .vcdtab import read_vcd


@dataclass(frozen=True)
class Signal:
    name: str
    direction: str
    clock: str | None


@dataclass(frozen=True)
class Literal:
    signal: str
    positive: bool = True

    def __str__(self) -> str:
        return self.signal if self.positive else f"!{self.signal}"

    def negate(self) -> Literal:
        return Literal(self.signal, not self.positive)


@dataclass(frozen=True)
class Candidate:
    template: str
    antecedent: tuple[Literal, ...]
    consequent: Literal

    def __post_init__(self):
        arity = {"always": 0, "implies": 1, "next": 1, "and": 2,
                 "and_next": 2, "mixed_next": 2}
        if self.template not in arity:
            raise ValueError(f"unknown assumption template '{self.template}'")
        if len(self.antecedent) != arity[self.template]:
            raise ValueError(f"template '{self.template}' needs {arity[self.template]} antecedents")

    @property
    def signals(self) -> tuple[str, ...]:
        return tuple(a.signal for a in self.antecedent + (self.consequent,))

    def __str__(self) -> str:
        a = self.antecedent
        if self.template == "always":
            return f"always {self.consequent}"
        if self.template == "implies":
            return f"always {a[0]} -> {self.consequent}"
        if self.template == "next":
            return f"always {a[0]} -> next {self.consequent}"
        if self.template == "and":
            return f"always ({a[0]} && {a[1]}) -> {self.consequent}"
        if self.template == "and_next":
            return f"always ({a[0]} && {a[1]}) -> next {self.consequent}"
        return f"always ({a[0]} && next {a[1]}) -> next {self.consequent}"

    def params(self, clock: str) -> dict:
        literal = lambda a: {"signal": a.signal, "positive": a.positive}  # noqa: E731
        return {"protocol": self.template, "clock": clock,
                "antecedent": [literal(a) for a in self.antecedent],
                "consequent": literal(self.consequent), "verify": False, "source": "inferred"}

    @classmethod
    def from_params(cls, params: dict) -> Candidate:
        def literal(data):
            return Literal(str(data["signal"]), bool(data.get("positive", True)))
        return cls(str(params["protocol"]), tuple(literal(a) for a in params.get("antecedent") or []),
                   literal(params["consequent"]))


@dataclass
class MiningResult:
    candidates: list[Candidate]
    implications: dict[Candidate, list[Candidate]]
    rejected: dict[str, list[Candidate]] = field(default_factory=dict)
    mined: int = 0


def _rank(signals: dict[str, Signal], name: str) -> tuple[int, str]:
    return (1 if signals[name].direction == "input" else 0, name)


def unique(candidate: Candidate, signals: dict[str, Signal]) -> bool:
    a = candidate.antecedent
    if candidate.template == "implies":
        return _rank(signals, a[0].signal) < _rank(signals, candidate.consequent.signal)
    if candidate.template == "and":
        names = [a[0].signal, a[1].signal, candidate.consequent.signal]
        return all(_rank(signals, x) < _rank(signals, y) for x, y in zip(names, names[1:]))
    if candidate.template == "and_next":
        return _rank(signals, a[0].signal) < _rank(signals, a[1].signal)
    if candidate.template == "mixed_next":
        return _rank(signals, a[1].signal) < _rank(signals, candidate.consequent.signal)
    return True


def _atoms(row: dict[str, int], signals: list[Signal]) -> tuple[list[Literal], list[Literal]]:
    true, false = [], []
    for signal in signals:
        value = row.get(signal.name)
        if value not in (0, 1):
            continue
        true.append(Literal(signal.name, bool(value)))
        false.append(Literal(signal.name, not bool(value)))
    return true, false


def mine_trace(rows: list[dict[str, int]], signal_list: list[Signal]) -> set[Candidate]:
    """Candidates whose negation occurs at least once in this counterexample."""
    signals = {s.name: s for s in signal_list}
    ordered = sorted(signal_list, key=lambda s: _rank(signals, s.name))
    atoms = [_atoms(row, ordered) for row in rows]
    out: set[Candidate] = set()
    for true, false in atoms:
        out.update(Candidate("always", (), c) for c in false)
        for a in true:
            out.update(Candidate("implies", (a,), c) for c in false
                       if _rank(signals, a.signal) < _rank(signals, c.signal))
        for a, b in combinations(true, 2):
            out.update(Candidate("and", (a, b), c) for c in false
                       if _rank(signals, b.signal) < _rank(signals, c.signal))
    for (true0, _), (true1, false1) in zip(atoms, atoms[1:]):
        for a in true0:
            out.update(Candidate("next", (a,), c) for c in false1)
        for a, b in combinations(true0, 2):
            out.update(Candidate("and_next", (a, b), c) for c in false1)
        for a in true0:
            for b in true1:
                out.update(Candidate("mixed_next", (a, b), c) for c in false1
                           if _rank(signals, b.signal) < _rank(signals, c.signal))
    return out


def implies(strong: Candidate, weak: Candidate) -> bool:
    """Syntactic implication from Plassan appendix E; strong |= weak."""
    if strong == weak:
        return False
    sa, sc = strong.antecedent, strong.consequent
    wa, wc = weak.antecedent, weak.consequent
    if strong.template == "always":
        if weak.template == "always":
            return False
        return wc == sc or any(a == sc.negate() for a in wa)
    if strong.template == "implies":
        a, b = sa[0], sc
        if weak.template == "and":
            return ((a in wa and wc == b) or (b in wa and wc == b)
                    or (a in wa and b.negate() in wa))
        if weak.template == "and_next":
            return a in wa and b.negate() in wa
        if weak.template == "mixed_next":
            return wa[1] == a and wc == b
    if strong.template == "next":
        a, b = sa[0], sc
        if weak.template == "and_next":
            return a in wa and wc == b
        if weak.template == "mixed_next":
            return (wa[0] == a and wc == b) or (wa[0] == a and wa[1] == b.negate())
    return False


def implication_map(candidates: list[Candidate]) -> dict[Candidate, list[Candidate]]:
    return {strong: [weak for weak in candidates if implies(strong, weak)]
            for strong in candidates
            if any(implies(strong, weak) for weak in candidates)}


def mine(traces: list[list[dict[str, int]]], signal_list: list[Signal],
         common_threshold: float = 1.0) -> MiningResult:
    """Apply input, uniqueness and common-cause filters, then build implications."""
    if not traces:
        return MiningResult([], {}, {"input": [], "uniqueness": [], "common_cause": []})
    if not 0 < common_threshold <= 1:
        raise ValueError("common_threshold must be in (0, 1]")
    signals = {s.name: s for s in signal_list}
    per_trace = [mine_trace(rows, signal_list) for rows in traces]
    union = set().union(*per_trace)
    input_ok = {c for c in union if signals[c.consequent.signal].direction == "input"}
    unique_ok = {c for c in input_ok if unique(c, signals)}
    needed = max(1, math.ceil(len(traces) * common_threshold))
    common = [c for c in unique_ok if sum(c in found for found in per_trace) >= needed]
    common.sort(key=str)
    return MiningResult(
        common, implication_map(common),
        {"input": sorted(union - input_ok, key=str),
         "uniqueness": sorted(input_ok - unique_ok, key=str),
         "common_cause": sorted(unique_ok - set(common), key=str)},
        mined=len(union))


def design_signals(cfg, nl, include_async: bool = False) -> list[Signal]:
    """Top-level I/O bits with a declared clock domain."""
    protected = {c.port for c in cfg.clocks} | {r.port for r in cfg.resets}
    input_clocks = {i.port: i.clock for i in cfg.inputs}
    out = []
    for port in nl.ports.values():
        if port.name in protected or port.direction not in ("input", "output"):
            continue
        clock = input_clocks.get(port.name) if port.direction == "input" else cfg.outputs.get(port.name)
        if clock is None and not (include_async and port.direction == "input"):
            continue
        for bit in range(port.width):
            name = port.name if port.width == 1 else f"{port.name}[{bit}]"
            out.append(Signal(name, port.direction, clock))
    return sorted(out, key=lambda s: (s.clock or "", s.direction, s.name))


def _wrapper_net(signal: Signal) -> str:
    base = signal.name.split("[", 1)[0]
    return f"ofcdc_{'in' if signal.direction == 'input' else 'out'}_{base}"


def _bit(row: dict, signal: Signal) -> int | None:
    raw = row.get(_wrapper_net(signal))
    if raw is None:
        return None
    try:
        value = int(raw, 16) if raw.startswith("0x") else int(raw, 2)
    except ValueError:
        return None
    match = re.search(r"\[(\d+)\]$", signal.name)
    bit = int(match.group(1)) if match else 0
    return (value >> bit) & 1


def _one(row: dict, name: str) -> bool:
    raw = row.get(name)
    if raw is None:
        return False
    try:
        return (int(raw, 16) if raw.startswith("0x") else int(raw, 2)) == 1
    except ValueError:
        return False


def sample_trace(path: str | Path, signals: list[Signal], clock: str) -> list[dict[str, int]]:
    """I/O values after every active edge of one domain, including repeated values."""
    domain = [s for s in signals if s.clock == clock]
    edge = f"ofcdc_edge_{clock}"
    _, rows = read_vcd(path, ["ofcdc_init_done", edge] + [_wrapper_net(s) for s in domain])
    out = []
    for _, row in rows:
        if not _one(row, "ofcdc_init_done") or not _one(row, edge):
            continue
        values = {s.name: value for s in domain if (value := _bit(row, s)) is not None}
        if values:
            out.append(values)
    return out


def blocking_steps(path: str | Path, signals: list[Signal]) -> list[dict[str, int]]:
    """Full global-step input sequence from the first active step."""
    inputs = [s for s in signals if s.direction == "input"]
    _, rows = read_vcd(path, ["ofcdc_init_done"] + [_wrapper_net(s) for s in inputs])
    out = []
    for _, row in rows:
        if not _one(row, "ofcdc_init_done"):
            continue
        values = {s.name: value for s in inputs if (value := _bit(row, s)) is not None}
        if values:
            out.append(values)
    return out


@dataclass
class FormalAnswer:
    value: str
    quality: float | None = None
    detail: str = ""


@dataclass
class CandidateResult:
    candidate: Candidate
    status: str
    reason: str
    quality: float | None
    filters: dict[str, str]
    implied_by: list[str]
    details: dict[str, str] = field(default_factory=dict)


def formal_filters(mined: MiningResult, evaluate, evaluate_many=None) -> list[CandidateResult]:
    """Filters 5-8, reusing consequences through the syntactic implication map."""
    candidates = mined.candidates
    weaker = {c: list(mined.implications.get(c, [])) for c in candidates}
    stronger = {c: [s for s in candidates if c in weaker[s]] for c in candidates}
    states = {name: {} for name in ("triviality", "consistency", "vacuity", "assertion")}
    answers = {name: {} for name in states}
    reject_value = {"triviality": "trivial", "consistency": "inconsistent", "vacuity": "vacuous"}
    blocked = set()

    def propagate(stage, seeds, value, related):
        for candidate in [seeds] + related[seeds]:
            if candidate not in states[stage]:
                states[stage][candidate] = value

    for stage in states:
        pending = [c for c in candidates if c not in blocked and c not in states[stage]]
        while pending:
            batch = []
            for candidate in pending:
                if all(candidate not in weaker[other] and candidate not in stronger[other]
                       for other in batch):
                    batch.append(candidate)
            if evaluate_many is not None:
                answers[stage].update(evaluate_many(batch, stage))
            for candidate in batch:
                answer = answers[stage].get(candidate)
                if answer is None:
                    answer = evaluate(candidate, stage)
                    answers[stage][candidate] = answer
                if stage == "triviality" and answer.value == "trivial":
                    propagate(stage, candidate, "trivial", weaker)
                elif stage == "triviality" and answer.value == "nontrivial":
                    propagate(stage, candidate, "nontrivial", stronger)
                elif stage == "consistency" and answer.value == "inconsistent":
                    propagate(stage, candidate, "inconsistent", stronger)
                elif stage == "vacuity" and answer.value == "vacuous":
                    propagate(stage, candidate, "vacuous", stronger)
                elif stage == "vacuity" and answer.value == "nonvacuous":
                    propagate(stage, candidate, "nonvacuous", weaker)
                elif stage == "assertion" and answer.value == "proven":
                    propagate(stage, candidate, "proven", stronger)
                else:
                    states[stage][candidate] = answer.value
            pending = [c for c in pending if c not in states[stage]]
        for candidate in candidates:
            if candidate in blocked or candidate not in states[stage]:
                continue
            if states[stage][candidate] in set(reject_value.values()) | {"unknown", "timeout", "error"}:
                blocked.add(candidate)
    out = []
    for candidate in candidates:
        filters = {stage: values.get(candidate, "not_run") for stage, values in states.items()}
        status, reason, quality = "candidate", "", None
        for stage, value in filters.items():
            if stage in reject_value and value == reject_value[stage]:
                status, reason = "rejected", stage
                break
            if value in ("unknown", "timeout", "error"):
                status, reason = "unknown", stage
                break
            if stage == "assertion":
                if value == "proven":
                    quality = 1.0
                elif value == "cex":
                    answer = answers[stage].get(candidate)
                    quality = answer.quality if answer else None
                else:
                    status, reason = "unknown", stage
        details = {stage: answers[stage][candidate].detail for stage in answers
                   if candidate in answers[stage] and answers[stage][candidate].detail}
        out.append(CandidateResult(candidate, status, reason, quality, filters,
                                   [str(s) for s in stronger[candidate]], details))
    return out
