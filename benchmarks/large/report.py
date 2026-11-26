#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Summarize large CDC benchmark results without inventing real-IP ground truth."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LARGE = ROOT / "benchmarks" / "large"
TOOLS = ("ofcdc", "jasper")
NAMES = {"ofcdc": "Open Formal CDC", "jasper": "Jasper CDC"}


def raw_of(run: dict) -> dict:
    return run["raw"]


def metrics(tool: str, raw: dict) -> dict:
    if tool == "ofcdc":
        return {"checks": dict(Counter(r["status"] for r in raw.get("results", []))),
                "crossing_verdicts": dict(Counter(r["verdict"] for r in raw.get("crossings", [])))}
    if tool == "jasper":
        return {"properties": dict(Counter(r["status"] for r in raw.get("properties", []))),
                "violations": dict(Counter(r.get("Check", "") for r in raw.get("violations", [])))}
    return {}


def detect(case_id: str, tool: str, raw: dict, baseline_raw: dict | None = None) -> str:
    if case_id == "cdc_array/binary":
        if tool == "ofcdc":
            hit = any(r["check"].startswith("gray_ptr_a_") and r["status"] == "cex"
                      for r in raw.get("results", []))
        elif tool == "jasper":
            hit = any("bus_gray_coded" in r["name"] and r["status"] == "cex" for r in raw.get("properties", []))
        else:
            hit = False
        if hit and baseline_raw is not None:
            baseline_hit = detect(case_id, tool, baseline_raw) == "1/1"
            if baseline_hit:
                return "0/1 (base also cex)"
        return "1/1" if hit else "0/1"
    if case_id == "cdc_array/missing_stage":
        if tool == "ofcdc":
            hit = any(r["verdict"] == "no_scheme" for r in raw.get("crossings", []))
        elif tool == "jasper":
            hit = any(r.get("Check") == "no_scheme" for r in raw.get("violations", []))
        else:
            hit = False
        return "1/1" if hit else "0/1"
    return "n/a"


def count_text(values: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(values.items()) if k) or "none"


def main() -> int:
    suite = json.loads((LARGE / "suite.json").read_text(encoding="utf-8"))
    output = {"schema": 1, "suite": suite["name"], "cases": []}
    totals = {tool: {"seconds": 0.0, "runs": 0, "errors": 0} for tool in TOOLS}
    for case in suite["cases"]:
        case_out = {"case": case["id"], "tools": {}}
        for tool in TOOLS:
            path = LARGE / "results" / case["id"].replace("/", "__") / f"{tool}.json"
            if not path.exists():
                case_out["tools"][tool] = {"status": "not_run"}
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            raw = raw_of(result["runs"][-1])
            baseline_raw = None
            if case["id"].startswith("cdc_array/") and case["variant"] != "base":
                baseline_path = LARGE / "results" / "cdc_array__base" / f"{tool}.json"
                if baseline_path.exists():
                    baseline_raw = raw_of(json.loads(baseline_path.read_text(encoding="utf-8"))["runs"][-1])
            measured = [r["seconds"] for r in result["runs"] if r["seconds"] is not None]
            seconds = result["seconds"] if result["seconds"] is not None else (statistics.median(measured) if measured else None)
            case_out["tools"][tool] = {"status": result["status"], "seconds": seconds,
                                       "fault_score": detect(case["id"], tool, raw, baseline_raw),
                                       "metrics": metrics(tool, raw),
                                       "job_parallel": result.get("job_parallel")}
            totals[tool]["seconds"] += seconds or 0.0
            totals[tool]["runs"] += len(result["runs"])
            totals[tool]["errors"] += result["status"] != "completed"
        output["cases"].append(case_out)
    output["totals"] = totals
    (LARGE / "results").mkdir(parents=True, exist_ok=True)
    (LARGE / "results" / "summary.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    lines = ["# Large CDC benchmark results", "",
             "Real-IP cases have no reviewed fault ledger and are reported by analysis counts, not confirmed bugs.",
             "Synthetic fault scores use the known binary and missing-stage mutations.", "",
             "| Case | Tool | Known faults found | Checks / properties | Violations / verdicts | Jobs | Time |",
             "|---|---|---:|---|---|---:|---:|"]
    for case in output["cases"]:
        for tool in TOOLS:
            row = case["tools"][tool]
            if row["status"] == "not_run":
                continue
            m = row["metrics"]
            if tool == "ofcdc":
                checks, other = count_text(m["checks"]), count_text(m["crossing_verdicts"])
            elif tool == "jasper":
                checks, other = count_text(m["properties"]), count_text(m["violations"])
            else:
                raise ValueError(tool)
            duration = "n/a" if row["seconds"] is None else f"{row['seconds']:.2f} s"
            parallel = row.get("job_parallel")
            jobs = str(parallel) if tool == "ofcdc" and parallel is not None else "n/a"
            tool_name = NAMES[tool] + (" (no waiver proof)" if case["case"] == "axi_spi/base" and tool == "jasper" else "")
            tool_name += " (TIMEOUT)" if row["status"] == "timeout" else ""
            lines.append(f"| {case['case']} | {tool_name} | {row['fault_score']} | {checks} | {other} | {jobs} | {duration} |")
    lines += ["", "Total case time is the sum of per-case wall-clock times.", "",
              "## Aggregate runtime", "", "| Tool | Runs | Errors/timeouts | Total case time |",
              "|---|---:|---:|---:|"]
    for tool in TOOLS:
        t = totals[tool]
        lines.append(f"| {NAMES[tool]} | {t['runs']} | {t['errors']} | {t['seconds']:.2f} s |")
    (LARGE / "results" / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
