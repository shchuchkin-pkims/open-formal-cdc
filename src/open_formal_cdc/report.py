# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Text report: checks, assumptions and crossing verdicts."""

from __future__ import annotations

from .flow import RunResult


def cell(status: str, step: int | None = None) -> str:
    if status == "model_mismatch":
        return "MODEL_MISMATCH"
    return f"{status}@{step}" if status == "cex" and step is not None else status


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(str(r[i])) for r in rows + [head]) for i in range(len(head))]
    fmt = lambda r: "  ".join(str(x).ljust(w) for x, w in zip(r, widths)).rstrip()  # noqa: E731
    return [fmt(head), fmt(["-" * w for w in widths])] + [fmt(r) for r in rows]


def _mark(ok: bool | None) -> str:
    return "" if ok is None else ("ok" if ok else "MISMATCH")


def text(result: RunResult, models: list[str]) -> str:
    lines: list[str] = []
    rows = []
    for o in result.outcomes:
        per = {m.model: cell(m.status, m.step) for m in o.models}
        name = (o.check if o.kind == "check" else
                f"{o.check} (no MSI)" if o.kind == "msi_baseline" else f"{o.check} (assumption)")
        rows.append([o.variant, name, o.template] + [per.get(m, "-") for m in models]
                    + [cell(o.status), o.expect or "-", _mark(o.ok)])
    if rows:
        lines += ["Checks:"] + _table(["variant", "check", "template"] + models
                                      + ["outcome", "expected", ""], rows)
    if result.verdicts:
        rows = [[v.variant, v.crossing, v.scheme, v.verdict, v.expect or "-", _mark(v.ok),
                 "; ".join(v.reasons)] for v in result.verdicts]
        lines += ["", "Crossings:"] + _table(["variant", "crossing", "scheme", "verdict", "expected", "",
                                               "reasons"], rows)
    if any(result.states.values()):
        rows = [[vn, a, s] for vn, st in result.states.items() for a, s in st.items()]
        lines += ["", "Assumptions:"] + _table(["variant", "assumption", "state"], rows)
    baselines = [o for o in result.outcomes if o.kind == "msi_baseline"]
    if baselines:
        rows = []
        for baseline in baselines:
            main = next(o for o in result.outcomes
                        if o.variant == baseline.variant and o.kind == "check" and o.check == baseline.baseline_of)
            if baseline.status == "proven" and main.status == "cex":
                reading = "sensitive"
            elif baseline.status == main.status == "proven":
                reading = "robust"
            else:
                reading = "unresolved"
            rows.append([baseline.variant, baseline.baseline_of, cell(baseline.status), cell(main.status), reading])
        lines += ["", "MSI ablation:"] + _table(["variant", "check", "no MSI", "with MSI", "reading"], rows)
    details = []
    for o in result.outcomes:
        for m in o.models:
            if m.status in ("cex", "vacuous", "error", "unknown") and m.detail:
                details.append(f"  {o.variant}/{o.check} [{m.model}]: {m.detail}"
                               + (f"\n    trace: {m.trace}" if m.trace else ""))
    if details:
        lines += ["", "Details:"] + details
    n_exp = sum(1 for o in result.outcomes if o.ok is not None) + sum(1 for v in result.verdicts if v.ok is not None)
    n_ok = sum(1 for o in result.outcomes if o.ok) + sum(1 for v in result.verdicts if v.ok)
    lines += ["", f"Jobs: {len(result.outcomes)}; crossings: {len(result.verdicts)}; "
              f"as expected: {n_ok}/{n_exp}" + (f"; MISMATCHES: {result.mismatches}" if result.mismatches else "")]
    return "\n".join(lines)


def structure_text(st, checks, assumptions) -> str:
    """Table of crossings found by the structural analysis."""
    if st is None:
        return "structural analysis is off"
    rows = [[x.name, f"{x.src_domain}->{x.dst_domain}", x.scheme, str(len({d for _, d in x.bits})),
             x.logic, " > ".join(x.stages) or (f"en={x.enable}" if x.enable else "-"), "; ".join(x.notes)]
            for x in st.crossings]
    lines = _table(["crossing", "domains", "scheme", "bits", "path", "stages / enable", "notes"], rows)
    if st.reset_crossings:
        reset_rows = [[x.name, f"{x.src_reset or '-'} ({x.src_reset_active})",
                       f"{x.dst_reset or '-'} ({x.dst_reset_active})",
                       f"{x.dst_valid} ({x.dst_valid_active})" if x.dst_valid else "always"]
                      for x in st.reset_crossings]
        lines += ["", "Reset-domain crossings:"] + _table(
            ["crossing", "source reset", "destination reset", "capture"], reset_rows)
    if st.reset_signals:
        reset_rows = [[x.src, x.src_clock or "unknown", x.dst_clock or "unknown", x.active,
                       ", ".join(x.consumers)] for x in st.reset_signals]
        lines += ["", "Reset signal crossings:"] + _table(
            ["reset", "source clock", "destination clock", "active", "consumers"], reset_rows)
    if st.reset_polarities:
        polarity_rows = [[x.kind, x.src, x.dst, x.expected, x.actual, x.reset] for x in st.reset_polarities]
        lines += ["", "Reset polarity mismatches:"] + _table(
            ["kind", "source", "destination", "expected", "actual", "reset"], polarity_rows)
    if st.reset_chains:
        chain_rows = [[x.reset, x.clock or "unknown", x.head, x.tail, ", ".join(x.consumers)]
                      for x in st.reset_chains]
        lines += ["", "Reset chains:"] + _table(["reset", "clock", "head", "tail", "consumers"], chain_rows)
    if st.reset_domain_misses:
        miss_rows = [[x.reset, ", ".join(x.chains), ", ".join(x.missing), ", ".join(x.consumers)]
                     for x in st.reset_domain_misses]
        lines += ["", "Missing reset domains:"] + _table(["reset", "synchronized domains", "raw domains", "consumers"], miss_rows)
    if st.reset_dual_uses:
        dual_rows = [[x.src, x.async_user, ", ".join(x.sync_users)] for x in st.reset_dual_uses]
        lines += ["", "Dual-use resets:"] + _table(["reset", "async consumer", "sync consumers"], dual_rows)
    if st.reset_stuck:
        stuck_rows = [[x.head, ", ".join(x.consumers), x.reset or "unknown", x.reset_active, str(x.value)]
                      for x in st.reset_stuck]
        lines += ["", "Stuck reset chains:"] + _table(
            ["head", "consumers", "reset", "active", "asserted value"], stuck_rows)
    if st.reset_logic:
        logic_rows = [[x.kind, x.cell, x.dst, ", ".join(x.sources)] for x in st.reset_logic]
        lines += ["", "Reset logic:"] + _table(["rule", "cell", "destination", "sources"], logic_rows)
    if st.clock_muxes:
        mux_rows = [[x.name, x.output, x.select, ", ".join(x.clocks),
                     "static" if x.select_static else "free"] for x in st.clock_muxes]
        lines += ["", "Clock muxes:"] + _table(
            ["crossing", "output", "select", "clocks", "select mode"], mux_rows)
    lines += ["", "Schemes: " + ", ".join(f"{k}={v}" for k, v in sorted(st.counts.items()))]
    if st.convergence:
        lines += ["Convergence:"] + [f"  at {g['at']}: {', '.join(g['crossings'])}" for g in st.convergence]
    if st.divergence:
        lines += ["Divergence:"] + [f"  {d['src']}: {', '.join(d['crossings'])}" for d in st.divergence]
    if st.warnings:
        lines += ["Warnings:"] + [f"  {w}" for w in st.warnings]
    if checks:
        lines += ["Proposed checks:"] + [f"  {c.name}: {c.template} {c.params}" for c in checks]
    if assumptions:
        lines += ["Assumptions:"] + [f"  {a.name}: {a.kind} {a.params}" for a in assumptions]
    return "\n".join(lines)
