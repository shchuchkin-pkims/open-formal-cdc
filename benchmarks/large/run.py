#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Run large synthetic and real-IP CDC cases with all supported tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks"
LARGE = BENCH / "large"
sys.path.insert(0, str(ROOT))

from benchmarks.run import (JASPER_MODULE, apply_engine_override, commercial_command,
                            parse_jasper, run_command)

TOOLS = ("ofcdc", "jasper")


def load_case(case: dict):
    from open_formal_cdc.config import load_config, variant_design

    cfg = load_config(ROOT / case["config"])
    variant = next(v for v in cfg.variants if v.name == case["variant"])
    return cfg, variant, variant_design(cfg, variant)


def prepare_sources(case: dict, work: Path) -> tuple[list[Path], Path]:
    cfg, _, design = load_case(case)
    if case["id"].startswith("cdc_array"):
        source = design.files[0]
        text = source.read_text(encoding="utf-8")
        for name, value in design.params.items():
            pattern = re.compile(rf"(parameter\s+(?:int|bit)\s+{re.escape(name)}\s*=\s*)[^,)\n]+")
            text, count = pattern.subn(lambda m: m.group(1) + str(value), text)
            if not count:
                raise ValueError(f"{case['id']}: parameter {name} not found")
        rtl_dir = work / "rtl"
        rtl_dir.mkdir(parents=True, exist_ok=True)
        rtl = rtl_dir / source.name
        rtl.write_text(text, encoding="utf-8")
        filelist = work / "sources.f"
        filelist.write_text(str(rtl) + "\n", encoding="utf-8")
        return [rtl], filelist
    filelist = cfg.path.parent / "rtl.f"
    return design.files, filelist


def jasper_script(cfg, files: list[Path]) -> str:
    options = []
    for arg in cfg.design.slang_args:
        if arg.startswith("-I"):
            options.append("+incdir+" + arg[2:])
        elif arg.startswith("-D"):
            options.append("+define+" + arg[2:])
        else:
            raise ValueError(f"unsupported Jasper source option: {arg}")
    lines = ["clear -all", "analyze -sv12 " + " ".join(options + [str(f) for f in files]),
             f"elaborate -top {cfg.design.top}"]
    for clock in cfg.clocks:
        lines.append(f"clock {clock.port} -factor {clock.period:g}" if clock.period is not None
                     else f"clock {clock.port}")
    resets = [f"~{r.port}" if r.active_low else r.port for r in cfg.resets]
    lines.append("reset -expression " + " ".join(resets) + " -max_iterations 500")
    by_clock: dict[str, list[str]] = {}
    for port in cfg.inputs:
        by_clock.setdefault(port.clock, []).append(port.port)
    for clock, ports in by_clock.items():
        lines.append(f"clock -rate {{{' '.join(ports)}}} {cfg.clock(clock).port}")
    lines += [
        "check_cdc -check -severity {fatal {no_scheme}}",
        "check_cdc -check -severity {error {cdc_pair_logic sync_chain_logic}}",
        "check_cdc -check -severity {warning {cdc_pair_fanout sync_chain_fanout}}",
        "check_cdc -clock_domain -find", "check_cdc -pair -find", "check_cdc -scheme -find",
        "check_cdc -group -find", "check_cdc -protocol_check -generate", "check_cdc -waiver -generate",
        "check_cdc -report violations -file violations_structural.csv -force",
        "report -summary -results -file summary_structural.rpt -force",
        "set_prove_per_property_time_limit 30s", "set_prove_time_limit 2m",
    ]
    if cfg.path.parent.name == "axi_spi":
        lines.append("set_engine_mode {B}")
    lines += [
        "check_cdc -protocol_check -prove",
        "check_cdc -report violations -file violations_protocol.csv -force",
        "report -summary -results -file summary_protocol.rpt -force",
    ]
    if cfg.path.parent.name != "axi_spi":
        lines.append("check_cdc -waiver -prove")
    lines += [
        "check_cdc -report violations -file violations.csv -force",
        "report -summary -results -file summary.rpt -force", "exit -force",
    ]
    return "\n".join(lines) + "\n"


def run_ofcdc(case: dict, work: Path, files: list[Path], parallel: int) -> dict:
    from open_formal_cdc import __version__
    from open_formal_cdc.executor import make_executor
    from open_formal_cdc.flow import run

    cfg, variant, _ = load_case(case)
    apply_engine_override(cfg)
    cfg.design.files = files
    cfg.variants = [variant]
    out = work / "ofcdc"
    start = time.monotonic()
    result = run(cfg, out, make_executor("local"), parallel=parallel, log=lambda _: None)
    seconds = time.monotonic() - start
    raw = json.loads((out / "results.json").read_text(encoding="utf-8"))
    raw["tool_version"] = __version__
    raw["returncode"] = 0
    return {"raw": raw, "seconds": seconds, "status": "completed", "mismatches": result.mismatches}


def execute_one(case: dict, tool: str, work: Path, timeout: int, parallel: int) -> dict:
    files, filelist = prepare_sources(case, work)
    if tool == "ofcdc":
        result = run_ofcdc(case, work, files, parallel)
    else:
        if tool != "jasper":
            raise ValueError(f"unsupported tool: {tool}")
        tool_work = work / tool
        tool_work.mkdir(parents=True, exist_ok=True)
        script = tool_work / "run.tcl"
        script.write_text(jasper_script(load_case(case)[0], files), encoding="utf-8")
        command = commercial_command(JASPER_MODULE, f"jg -cdc -batch {shlex.quote(str(script))} -proj project")
        start = time.monotonic()
        try:
            rc, seconds = run_command(command, tool_work, timeout)
        except subprocess.TimeoutExpired:
            rc, seconds = 124, time.monotonic() - start
        raw = parse_jasper(tool_work, rc)
        status = "completed" if rc == 0 else ("timeout" if rc == 124 else "error")
        result = {"raw": raw, "seconds": seconds, "status": status, "command": command}
    result["sources"] = [str(f) for f in files]
    return result


def execute(case: dict, tool: str, repeat: int, timeout: int, parallel: int) -> dict:
    case_work = LARGE / "build" / case["id"].replace("/", "__")
    runs = []
    for index in range(repeat):
        work = case_work if repeat == 1 else case_work / f"run_{index + 1}"
        result = execute_one(case, tool, work, timeout, parallel)
        result["run"] = index + 1
        runs.append(result)
        print(f"{case['id']} {tool} run {index + 1}: {result['status']}, {result['seconds']:.2f} s", flush=True)
    good = [r["seconds"] for r in runs if r["status"] == "completed"]
    measured = [r["seconds"] for r in runs if r["seconds"] is not None]
    digest = hashlib.sha256()
    for source in runs[-1]["sources"]:
        digest.update(Path(source).read_bytes())
    overall_status = ("completed" if len(good) == repeat else
                      "timeout" if any(r["status"] == "timeout" for r in runs) else "error")
    result = {"schema": 1, "suite": "large-cdc-v1", "case": case["id"], "tool": tool,
              "faults": case["faults"], "status": overall_status,
              "seconds": statistics.median(measured) if measured else None,
              "source_sha256": digest.hexdigest(), "host": platform.node(), "platform": platform.platform(),
              "cpu_count": os.cpu_count(), "runs": runs}
    result["job_parallel"] = parallel if tool == "ofcdc" else None
    out = LARGE / "results" / case["id"].replace("/", "__")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{tool}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tools", default="ofcdc", help="comma-separated: ofcdc,jasper")
    ap.add_argument("--case", action="append", help="case ID; repeatable, default all")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=600, help="outer timeout per commercial run in seconds")
    ap.add_argument("--parallel", type=int, default=8, help="OFCDC SBY jobs in parallel")
    args = ap.parse_args()
    if args.parallel < 1:
        ap.error("--parallel must be positive")
    tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    if not tools or any(t not in TOOLS for t in tools):
        ap.error("invalid --tools")
    suite = json.loads((LARGE / "suite.json").read_text(encoding="utf-8"))
    selected = set(args.case or [])
    cases = [c for c in suite["cases"] if not selected or c["id"] in selected]
    unknown = selected - {c["id"] for c in cases}
    if unknown:
        ap.error(f"unknown cases: {', '.join(sorted(unknown))}")
    failed = 0
    for case in cases:
        for tool in tools:
            try:
                result = execute(case, tool, args.repeat, args.timeout, args.parallel)
                failed += result["status"] != "completed"
            except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
                failed += 1
                print(f"{case['id']} {tool}: ERROR: {exc}", file=sys.stderr, flush=True)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
