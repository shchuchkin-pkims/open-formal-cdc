#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Run the directed CDC benchmark with Open Formal CDC and Jasper CDC."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks"
BUILD = BENCH / "build"
RESULTS = BENCH / "results"
TOOLS = ("ofcdc", "jasper")
JASPER_MODULE = "cadence/JasperGold/2019.06"


def load_suite() -> dict:
    return json.loads((BENCH / "suite.json").read_text(encoding="utf-8"))


def safe_name(case_id: str) -> str:
    return case_id.replace("/", "__")


def load_case(case: dict):
    from open_formal_cdc.config import load_config, variant_design

    cfg = load_config(ROOT / "examples" / case["example"] / "ofcdc.yaml")
    variant = next(v for v in cfg.variants if v.name == case["variant"])
    return cfg, variant, variant_design(cfg, variant)


def prepare_rtl(case: dict, case_work: Path) -> tuple[Path, dict]:
    _, _, design = load_case(case)
    if len(design.files) != 1:
        raise ValueError(f"{case['id']}: the directed runner expects one RTL source")
    source = design.files[0]
    text = source.read_text(encoding="utf-8")
    for name, value in design.params.items():
        pattern = re.compile(rf"(parameter\s+(?:int|bit)\s+{re.escape(name)}\s*=\s*)[^,)\n]+")
        text, count = pattern.subn(lambda m: m.group(1) + str(value), text)
        if not count:
            raise ValueError(f"{case['id']}: parameter {name} not found in {source}")
    rtl_dir = case_work / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    rtl = rtl_dir / source.name
    rtl.write_text(text, encoding="utf-8")
    return rtl, design.params


def tcl_list(values) -> str:
    return "{" + " ".join(str(v) for v in values) + "}"


def jasper_script(cfg, rtl: Path) -> str:
    lines = ["clear -all", f"analyze -sv12 {rtl}", f"elaborate -top {cfg.design.top}"]
    for clock in cfg.clocks:
        if clock.period is not None:
            lines.append(f"clock {clock.port} -factor {clock.period:g}")
        else:
            lines.append(f"clock {clock.port}")
    resets = [f"~{r.port}" if r.active_low else r.port for r in cfg.resets]
    if resets:
        lines.append("reset " + " ".join(resets))
    by_clock: dict[str, list[str]] = {}
    for port in cfg.inputs:
        by_clock.setdefault(port.clock, []).append(port.port)
    for clock, ports in by_clock.items():
        lines.append(f"clock -rate {tcl_list(ports)} {cfg.clock(clock).port}")
    if cfg.path.parent.name == "static_cfg":
        lines += ["check_cdc -signal_config -add_constant {{wr 0}}",
                  "check_cdc -signal_config -add_static {cfg}"]
    lines += [
        "check_cdc -check -severity {fatal {no_scheme}}",
        "check_cdc -check -severity {error {cdc_pair_logic sync_chain_logic}}",
        "check_cdc -check -severity {warning {cdc_pair_fanout sync_chain_fanout}}",
        "check_cdc -clock_domain -find", "check_cdc -pair -find", "check_cdc -scheme -find",
        "check_cdc -group -find", "check_cdc -protocol_check -generate", "check_cdc -waiver -generate",
        "set_prove_per_property_time_limit 30s", "set_prove_time_limit 2m",
        "check_cdc -protocol_check -prove", "check_cdc -waiver -prove",
    ]
    if cfg.path.parent.name == "static_cfg":
        lines.append("check_cdc -signal_config -prove")
    lines += ["check_cdc -report violations -file violations.csv -force",
              "report -summary -results -file summary.rpt -force", "exit -force"]
    return "\n".join(lines) + "\n"


def filtered_errors(log: Path) -> list[str]:
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "licen" in line.lower():
            continue
        if re.search(r"\b(error|fatal)\b", line, re.I):
            out.append(line)
    return out[-20:]


def parse_jasper(work: Path, returncode: int) -> dict:
    properties = []
    summary = next((p for p in (work / "summary.rpt", work / "summary_protocol.rpt",
                                work / "summary_structural.rpt") if p.exists()), work / "summary.rpt")
    if summary.exists():
        for line in summary.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*\[\d+\]\s+(\S+)\s+(proven|cex|ar_cex|undetermined|unprocessed|error|marked_proven)\b", line)
            if m:
                properties.append({"name": m.group(1), "status": m.group(2)})
    violations = []
    report = next((p for p in (work / "violations.csv", work / "violations_protocol.csv",
                               work / "violations_structural.csv") if p.exists()), work / "violations.csv")
    if report.exists():
        with report.open(encoding="utf-8", errors="replace", newline="") as f:
            violations = list(csv.DictReader(f))
    return {"returncode": returncode, "properties": properties, "violations": violations,
            "errors": filtered_errors(work / "run.log")}


def run_command(command: str, work: Path, timeout: int) -> tuple[int, float]:
    work.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with (work / "run.log").open("w", encoding="utf-8") as log:
        proc = subprocess.run(["bash", "-c", command], cwd=work, stdout=log, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False)
    return proc.returncode, time.monotonic() - start


def commercial_command(module: str, command: str) -> str:
    return ("type module >/dev/null 2>&1 || source /etc/profile.d/lmod.sh; "
            "export MODULEPATH=/opt/modulefiles${MODULEPATH:+:$MODULEPATH}; "
            f"module load {module}; {command}")


def apply_engine_override(cfg) -> None:
    engine = os.environ.get("OFCDC_PROVE_ENGINE")
    if engine:
        cfg.options.prove_engine = engine


def run_ofcdc(case: dict, case_work: Path, rtl: Path) -> dict:
    from open_formal_cdc import __version__
    from open_formal_cdc.executor import make_executor
    from open_formal_cdc.flow import run

    cfg, variant, _ = load_case(case)
    apply_engine_override(cfg)
    cfg.design.files = [rtl]
    cfg.variants = [variant]
    work = case_work / "ofcdc"
    start = time.monotonic()
    result = run(cfg, work, make_executor("local"), log=lambda _: None)
    seconds = time.monotonic() - start
    raw = json.loads((work / "results.json").read_text(encoding="utf-8"))
    raw.update({"returncode": 0, "tool_version": __version__})
    return {"raw": raw, "seconds": seconds, "status": "completed"}


def run_jasper(case: dict, cfg, case_work: Path, rtl: Path, timeout: int) -> dict:
    work = case_work / "jasper"
    work.mkdir(parents=True, exist_ok=True)
    script = work / "run.tcl"
    script.write_text(jasper_script(cfg, rtl), encoding="utf-8")
    command = commercial_command(JASPER_MODULE, f"jg -cdc -batch {shlex.quote(str(script))} -proj project")
    rc, seconds = run_command(command, work, timeout)
    return {"raw": parse_jasper(work, rc), "seconds": seconds,
            "status": "completed" if rc == 0 else "error", "command": command}


def execute(case: dict, tool: str, repeat: int, timeout: int) -> dict:
    case_work = BUILD / safe_name(case["id"])
    case_work.mkdir(parents=True, exist_ok=True)
    rtl, params = prepare_rtl(case, case_work)
    cfg, _, _ = load_case(case)
    runs = []
    for index in range(repeat):
        run_work = case_work if repeat == 1 else case_work / f"run_{index + 1}"
        if tool == "ofcdc":
            result = run_ofcdc(case, run_work, rtl)
        elif tool == "jasper":
            result = run_jasper(case, cfg, run_work, rtl, timeout)
        else:
            raise ValueError(f"unsupported tool: {tool}")
        result["run"] = index + 1
        runs.append(result)
        print(f"{case['id']} {tool} run {index + 1}: {result['status']}, {result['seconds']:.2f} s", flush=True)
    good_times = [r["seconds"] for r in runs if r["status"] == "completed"]
    result = {
        "schema": 1, "suite": "directed-cdc-v2", "case": case["id"], "tool": tool,
        "faults": case["faults"], "parameters": params,
        "status": "completed" if len(good_times) == repeat else "error",
        "seconds": statistics.median(good_times) if good_times else None,
        "source_sha256": hashlib.sha256(rtl.read_bytes()).hexdigest(),
        "host": platform.node(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "runs": runs,
    }
    out = RESULTS / safe_name(case["id"])
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{tool}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tools", default="ofcdc", help="comma-separated: ofcdc,jasper")
    ap.add_argument("--case", action="append", help="case ID; repeatable, default all")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=180, help="outer timeout per commercial run in seconds")
    args = ap.parse_args()
    tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    if not tools or any(t not in TOOLS for t in tools):
        ap.error(f"--tools must contain {', '.join(TOOLS)}")
    if args.repeat < 1:
        ap.error("--repeat must be positive")
    suite = load_suite()
    selected = set(args.case or [])
    cases = [c for c in suite["cases"] if not selected or c["id"] in selected]
    unknown = selected - {c["id"] for c in cases}
    if unknown:
        ap.error(f"unknown cases: {', '.join(sorted(unknown))}")
    failed = 0
    for case in cases:
        for tool in tools:
            try:
                result = execute(case, tool, args.repeat, args.timeout)
                failed += result["status"] != "completed"
            except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
                failed += 1
                print(f"{case['id']} {tool}: ERROR: {exc}", file=sys.stderr, flush=True)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
