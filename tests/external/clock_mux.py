#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-CLKMUX regression on public static-select and asynchronous-select cases."""

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

OUT = ROOT / "build" / "clock_mux"
CASE_IDS = ["fx_cdc010_good_static_select", "cdc010_async_select",
            "fx_cdc010_good_glitch_free_mux", "cdc010_leg_synced_select_runt"]
GOOD = {"fx_cdc010_good_static_select", "fx_cdc010_good_glitch_free_mux"}
PROTOCOL = {"fx_cdc010_good_glitch_free_mux", "cdc010_leg_synced_select_runt"}


def run_case(c: dict, executor_spec: str, models: list[str]) -> dict:
    netlist = json.loads((WORK / c["id"] / "netlist.json").read_text())
    resets = reset_ports(netlist, c["top"])
    protocol = c["id"] in PROTOCOL
    if protocol:
        resets += [("rst0", False), ("rst1", False)]
    reset_names = {name for name, _ in resets}
    clocks, inputs, _, _ = config_for(c)
    raw = {
        "design": {"top": c["top"], "files": [str((WORK / c["id"] / "design.sv").resolve())]},
        "clocks": [{"name": k.name, "port": k.port} for k in clocks],
        "resets": [{"port": name, "active": "low" if low else "high"} for name, low in resets],
        "inputs": [{"port": i.port, "clock": i.clock} for i in inputs if i.port not in reset_names],
        "options": {"time_models": models, "timeout": 60, "clock_mux_checks": True},
    }
    if protocol:
        raw["options"]["reset_steps"] = 30
        raw["options"]["prove_engine"] = "aiger rIC3"
        raw["options"]["timeout"] = 120
        raw["inputs"] = [i for i in raw["inputs"] if i["port"] != "sel_d"]
    out = OUT / c["id"]
    out.mkdir(parents=True, exist_ok=True)
    config_path = out / "ofcdc.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    cfg = parse_config(raw, config_path)
    result = run(cfg, out / "ofcdc", make_executor(executor_spec), log=lambda _: None)
    expected = "proven" if c["id"] in GOOD else "cex"
    checks = [o for o in result.outcomes if o.template == "clock_mux"]
    verdicts = [v for v in result.verdicts if v.scheme == "clock_mux"]
    expected_verdict = "safe_assuming" if expected == "proven" else "unsafe"
    ok = (len(checks) == 1 and checks[0].status == expected
          and len(verdicts) == 1 and verdicts[0].verdict == expected_verdict)
    return {"id": c["id"], "expected": expected, "expected_verdict": expected_verdict, "ok": ok,
            "status": checks[0].status if checks else "no_check",
            "verdict": verdicts[0].verdict if verdicts else "no_verdict"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--executor", default=os.environ.get("OFCDC_EXECUTOR", "local"))
    ap.add_argument("--case", action="append")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--models", default="clk2ff")
    ap.add_argument("-j", type=int, default=16)
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    repo = fetch()
    cs = cases(repo, args.case or CASE_IDS)
    if not args.no_build:
        build_netlists(cs, args.executor, args.j)
    with ThreadPoolExecutor(max_workers=len(cs)) as pool:
        report = list(pool.map(lambda c: run_case(c, args.executor, models), cs))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report:
        print(f"{'ok' if row['ok'] else 'FAIL'} {row['id']}: {row['status']}, {row['verdict']}")
    passed = sum(r["ok"] for r in report)
    print(f"T-CLKMUX: {passed}/{len(report)} cases as expected; report: {OUT / 'report.json'}")
    return int(passed != len(report))


if __name__ == "__main__":
    raise SystemExit(main())
