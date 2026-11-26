#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Score normalized benchmark results and generate Markdown tables."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks"
RESULTS = BENCH / "results"
TOOLS = ("ofcdc", "jasper")
TOOL_NAMES = {"ofcdc": "Open Formal CDC", "jasper": "Jasper CDC"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def latest_raw(result: dict) -> dict:
    return result["runs"][-1]["raw"]


def ofcdc_evidence(case: dict, fault: dict, raw: dict) -> list[str]:
    spec = fault["ofcdc"]
    names = spec["name"] if isinstance(spec["name"], list) else [spec["name"]]
    evidence = []
    for row in raw.get("results", []):
        if row.get("check") in names and row.get("status") == spec["status"]:
            evidence.append(f"{row['check']}:{row['status']}")
    return evidence


def ofcdc_m4_ablation(raw: dict) -> dict | None:
    rows = raw.get("results", [])
    hazard = next((r for r in rows if r.get("template") == "nohazard"), None)
    if hazard is None:
        return None
    glitch = next((r for r in rows if r.get("template") == "onechange"
                   and str(r.get("check", "")).startswith("glitch_")), None)
    onechange = glitch["status"] if glitch else "not_run"
    nohazard = hazard["status"]
    if onechange == "cex" and nohazard == "proven":
        reading = "discharged"
    elif nohazard == "cex":
        reading = "hazard_candidate"
    elif onechange == "proven" and nohazard == "proven":
        reading = "agree_safe"
    else:
        reading = "unresolved"
    return {"onechange": onechange, "nohazard": nohazard, "reading": reading}


def commercial_glitch_evidence(tool: str, raw: dict) -> list[str]:
    if tool == "jasper":
        return [f"{p['name']}:{p['status']}" for p in raw.get("properties", [])
                if "u_and" in p["name"] and "data_stable" in p["name"]]
    if tool != "jasper":
        raise ValueError(f"unsupported tool: {tool}")
    return []


def jasper_evidence(rule: dict, raw: dict) -> list[str]:
    evidence = []
    for prop in raw.get("properties", []):
        if fnmatch.fnmatchcase(prop["name"], rule.get("property", "*")) and prop["status"] in rule.get("status", []):
            evidence.append(f"{prop['name']}:{prop['status']}")
    for violation in raw.get("violations", []):
        check = violation.get("Check", "")
        if fnmatch.fnmatchcase(check, rule.get("violation", "")) and check:
            evidence.append(f"violation:{check}")
    return evidence


def score_fault(case: dict, fault: dict, tool: str, result: dict) -> dict:
    raw = latest_raw(result)
    if tool == "ofcdc":
        evidence = ofcdc_evidence(case, fault, raw)
    else:
        rule = fault.get(tool)
        if rule is None:
            return {"detected": None, "evidence": [], "reason": "not mapped"}
        evidence = jasper_evidence(rule, raw)
    return {"detected": bool(evidence), "evidence": evidence, "reason": ""}


def seconds_text(value) -> str:
    return "n/a" if value is None else f"{value:.2f} s"


def score_all(allow_partial: bool = False) -> dict:
    suite = load_json(BENCH / "suite.json")
    cases_out = []
    missing = []
    totals = {tool: {"detected": 0, "known": 0, "seconds": 0.0, "unscored": 0} for tool in TOOLS}
    by_design = defaultdict(lambda: {tool: {"detected": 0, "known": 0, "seconds": 0.0, "unscored": 0}
                                     for tool in TOOLS})
    ablation_totals = defaultdict(int)
    for case in suite["cases"]:
        case_out = {"case": case["id"], "tools": {}, "m4_ablation": None, "commercial_glitch": {}}
        for tool in TOOLS:
            path = RESULTS / case["id"].replace("/", "__") / f"{tool}.json"
            if not path.exists():
                missing.append(str(path.relative_to(ROOT)))
                case_out["tools"][tool] = {"status": "not_run"}
                continue
            result = load_json(path)
            if tool == "ofcdc":
                case_out["m4_ablation"] = ofcdc_m4_ablation(latest_raw(result))
                run_readings = [ofcdc_m4_ablation(latest_raw({"runs": [run]})) for run in result["runs"]]
                case_out["m4_ablation_runs"] = run_readings
                if case_out["m4_ablation"] and len({a["reading"] if a else None for a in run_readings}) > 1:
                    case_out["m4_ablation"]["reading"] = "unstable"
                if case_out["m4_ablation"]:
                    ablation_totals[case_out["m4_ablation"]["reading"]] += 1
            elif case_out["m4_ablation"]:
                case_out["commercial_glitch"][tool] = commercial_glitch_evidence(tool, latest_raw(result))
            faults = []
            for fault_id in case["faults"]:
                fault = dict(suite["faults"][fault_id])
                fault["id"] = fault_id
                scored = score_fault(case, fault, tool, result)
                run_scores = [score_fault(case, fault, tool, {"runs": [run]}) for run in result["runs"]]
                scored["run_detections"] = [r["detected"] for r in run_scores]
                if len(set(scored["run_detections"])) > 1:
                    scored["detected"] = False
                    scored["reason"] = "unstable verdict across repeated runs"
                baseline_path = RESULTS / f"{case['example']}__base" / f"{tool}.json"
                if baseline_path.exists() and case["variant"] != "base":
                    baseline = load_json(baseline_path)
                    baseline_scored = score_fault(case, fault, tool, baseline)
                    scored["baseline_evidence"] = baseline_scored["evidence"]
                    if scored["detected"] and baseline_scored["detected"]:
                        scored["detected"] = False
                        scored["reason"] = "signature also fires on the known-good control"
                scored["id"] = fault_id
                scored["claim"] = fault.get("claim", "sufficient_condition"
                                              if fault["class"] in ("glitch", "reconvergence") else "property")
                faults.append(scored)
                if scored["detected"] is None:
                    totals[tool]["unscored"] += 1
                    by_design[case["example"]][tool]["unscored"] += 1
                else:
                    totals[tool]["known"] += 1
                    by_design[case["example"]][tool]["known"] += 1
                    if scored["detected"]:
                        totals[tool]["detected"] += 1
                        by_design[case["example"]][tool]["detected"] += 1
            totals[tool]["seconds"] += result.get("seconds") or 0.0
            by_design[case["example"]][tool]["seconds"] += result.get("seconds") or 0.0
            case_out["tools"][tool] = {"status": result["status"],
                                       "seconds": result.get("seconds"), "faults": faults}
        cases_out.append(case_out)
    if missing and not allow_partial:
        raise FileNotFoundError("missing results: " + ", ".join(missing))
    return {"schema": 1, "suite": suite["name"], "cases": cases_out,
            "totals": totals, "designs": by_design, "m4_ablation": ablation_totals,
            "missing": missing}


def markdown(summary: dict) -> str:
    lines = ["# Directed CDC benchmark results", "",
             "Times are median wall-clock times of the recorded runs. Faults are scored by root cause.", ""]
    lines += ["| Case | Tool | Faults found | Time | Evidence |", "|---|---|---:|---:|---|"]
    for case in summary["cases"]:
        for tool in TOOLS:
            row = case["tools"][tool]
            if row["status"] == "not_run":
                found, duration, evidence = "Not run", "n/a", ""
            else:
                scored = [f for f in row["faults"] if f["detected"] is not None]
                found = str(sum(f["detected"] for f in scored)) + "/" + str(len(scored))
                if any(f["detected"] is None for f in row["faults"]):
                    found += " (partial)"
                duration = seconds_text(row["seconds"])
                evidence = "<br>".join(f"{f['id']} [{f['claim']}]: "
                                       f"{f['reason'] or (', '.join(f['evidence']) if f['evidence'] else 'not detected')}"
                                       for f in row["faults"])
            lines.append(f"| {case['case']} | {TOOL_NAMES[tool]} | {found} | {duration} | {evidence} |")
    lines += ["", "## Summary by design", "",
              "| Design | Open Formal CDC | Jasper CDC |", "|---|---:|---:|"]
    for design, tools in summary["designs"].items():
        cells = []
        for tool in TOOLS:
            t = tools[tool]
            duration = "n/a" if not t["known"] and t["unscored"] else seconds_text(t["seconds"])
            value = f"{t['detected']}/{t['known']}, {duration}"
            if t["unscored"]:
                value += f", {t['unscored']} unscored"
            cells.append(value)
        lines.append(f"| {design} | " + " | ".join(cells) + " |")
    lines += ["", "## Overall", "", "| Tool | Faults found | Total case time | Unscored |",
              "|---|---:|---:|---:|"]
    for tool in TOOLS:
        t = summary["totals"][tool]
        duration = "n/a" if not t["known"] and t["unscored"] else seconds_text(t["seconds"])
        lines.append(f"| {TOOL_NAMES[tool]} | {t['detected']}/{t['known']} | {duration} | {t['unscored']} |")
    ablation_cases = [c for c in summary["cases"] if c.get("m4_ablation")]
    if ablation_cases:
        lines += ["", "## M4 ablation (Open Formal CDC)", "",
                  "`onechange` is a sufficient-condition heuristic. `nohazard` checks the RTL function-hazard model; its counterexample is not a proof of a physical glitch. Commercial evidence is shown in the tools' native semantics and is not equivalent to an M4 verdict.", "",
                  "| Case | onechange | nohazard (M4) | Reading | Jasper data_stable |",
                  "|---|---|---|---|---|"]
        for case in ablation_cases:
            a = case["m4_ablation"]
            commercial = case["commercial_glitch"]
            jasper = ", ".join(commercial.get("jasper", [])) or "not detected"
            lines.append(f"| {case['case']} | {a['onechange']} | {a['nohazard']} | {a['reading']} | {jasper} |")
    if summary["missing"]:
        lines += ["", "Partial report. Missing: " + ", ".join(summary["missing"])]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allow-partial", action="store_true")
    args = ap.parse_args()
    summary = score_all(args.allow_partial)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "summary.md").write_text(markdown(summary), encoding="utf-8")
    print(markdown(summary), end="")
    return int(any(f["detected"] is None for c in summary["cases"] for t in c["tools"].values()
                   if t["status"] != "not_run" for f in t.get("faults", [])))


if __name__ == "__main__":
    raise SystemExit(main())
