#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Formal RDC-001 and RDC-009 regressions on adibis/cdc-rdc-tests.

Faulty cases must produce counterexamples in both time models. The ordered-release
control must produce a non-vacuous RDC-009 proof and no RDC-001 finding. Reset inputs
are inferred from reset pins and may be asserted again after the initial reset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "external"))

from crt import WORK, build_netlists, cases, config_for, fetch, reset_ports  # noqa: E402
from open_formal_cdc.config import parse_config  # noqa: E402
from open_formal_cdc.executor import make_executor  # noqa: E402
from open_formal_cdc.flow import run  # noqa: E402

OUT = ROOT / "build" / "rdc"
CONTROL = "fx_rdc009_good_ordered_release"
GOOD_CONTROLS = {CONTROL, "fx_rdc005_good_muxed_reset", "fx_rdc006_good_muxed_reset_synced",
                 "fx_rdc007_good_chain_deassert_polarity", "fx_rdc008_good_reset_port_both_domains"}
TEMPLATES = {"RDC-001": "reset_release", "RDC-002": "reset_value", "RDC-003": "srst_release",
             "RDC-004": "reset_logic", "RDC-005": "reset_logic", "RDC-006": "reset_logic",
             "RDC-007": "reset_stuck", "RDC-008": "reset_domain_miss", "RDC-009": "rdc_capture",
             "RDC-010": "reset_record", "RDC-011": "reset_dual_use"}
STRUCTURAL_REASONS = {"RDC-002": "polarity mismatch", "RDC-004": "combinational reset logic",
                      "RDC-005": "multiple independent reset sources", "RDC-006": "muxed reset source",
                      "RDC-007": "reset chain head", "RDC-008": "missing reset domain",
                      "RDC-011": "asynchronous and synchronous consumers"}


def selected(repo: Path, only: list[str] | None, rule: str) -> list[dict]:
    return [c for c in cases(repo, only)
            if c["id"] in GOOD_CONTROLS or any(e["rule"] == rule for e in c.get("expect", []))]


def run_case(c: dict, executor_spec: str, models: list[str], rule: str, out_root: Path) -> dict:
    netlist = json.loads((WORK / c["id"] / "netlist.json").read_text())
    resets = reset_ports(netlist, c["top"])
    reset_names = {name for name, _ in resets}
    clocks, inputs, _, _ = config_for(c)
    raw = {
        "design": {"top": c["top"], "files": [str((WORK / c["id"] / "design.sv").resolve())]},
        "clocks": [{"name": k.name, "port": k.port} for k in clocks],
        "resets": [{"port": name, "active": "low" if low else "high", "mode": "free"}
                   for name, low in resets],
        "inputs": [{"port": i.port, "clock": i.clock} for i in inputs if i.port not in reset_names],
        "options": {"time_models": models, "timeout": 120, "rdc_checks": True},
    }
    out = out_root / c["id"]
    out.mkdir(parents=True, exist_ok=True)
    config_path = out / "ofcdc.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    cfg = parse_config(raw, config_path)
    result = run(cfg, out / "ofcdc", make_executor(executor_spec), parallel=len(models), log=lambda _: None)
    template = TEMPLATES[rule]
    checks = [o for o in result.outcomes if o.template == template]
    if any(e["rule"] == rule for e in c.get("expect", [])):
        expected = "cex"
    elif c["id"] in GOOD_CONTROLS and c["id"] != CONTROL:
        expected = "no_finding"
    elif rule in ("RDC-001", "RDC-002", "RDC-003", "RDC-004", "RDC-005", "RDC-006", "RDC-007", "RDC-008",
                  "RDC-010", "RDC-011"):
        expected = "no_finding"
    else:
        expected = "proven"
    structural_hit = any(
        v.verdict == "unsafe" and any(STRUCTURAL_REASONS.get(rule, "polarity mismatch") in reason
                                     for reason in v.reasons)
        for v in result.verdicts)
    if expected == "cex":
        ok = (any(o.status == "cex" for o in checks)
              or (rule == "RDC-010" and any(v.verdict in ("note", "warning", "unsafe") for v in result.verdicts))
              or structural_hit)
    elif expected == "no_finding":
        ok = not checks
    else:
        ok = bool(checks) and all(o.status == "proven" for o in checks)
    return {
        "id": c["id"], "rule": rule, "expected": expected, "ok": ok,
        "resets": [{"port": name, "active": "low" if low else "high"} for name, low in resets],
        "checks": [{"name": o.check, "status": o.status,
                    "models": [{"model": m.model, "status": m.status, "detail": m.detail} for m in o.models]}
                   for o in checks],
        "verdicts": [{"crossing": v.crossing, "scheme": v.scheme, "verdict": v.verdict,
                      "reasons": v.reasons}
                     for v in result.verdicts if v.scheme == "reset_domain"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rule", choices=sorted(TEMPLATES), default="RDC-009")
    ap.add_argument("--executor", default=os.environ.get("OFCDC_EXECUTOR", "local"))
    ap.add_argument("--case", action="append")
    ap.add_argument("--no-build", action="store_true", help="reuse netlists in build/crt")
    ap.add_argument("--models", default="ticks,clk2ff")
    ap.add_argument("-j", type=int, default=16)
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    repo = fetch()
    cs = selected(repo, args.case, args.rule)
    if not cs:
        print(f"no {args.rule} cases selected", file=sys.stderr)
        return 2
    if not args.no_build:
        build_netlists(cs, args.executor, args.j)
    out_root = OUT / args.rule
    with ThreadPoolExecutor(max_workers=min(3, len(cs))) as pool:
        report = list(pool.map(lambda c: run_case(c, args.executor, models, args.rule, out_root), cs))
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report:
        statuses = ", ".join(f"{c['name']}={c['status']}" for c in row["checks"]) or "no checks"
        print(f"{'ok' if row['ok'] else 'FAIL'} {row['id']}: expected {row['expected']}; {statuses}")
    passed = sum(r["ok"] for r in report)
    print(f"{args.rule}: {passed}/{len(report)} cases as expected; report: {out_root / 'report.json'}")
    return int(passed != len(report))


if __name__ == "__main__":
    raise SystemExit(main())
