# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Tests for the directed benchmark manifest, parsers, and scoring."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_suite_matrix_is_complete():
    suite = json.loads((ROOT / "benchmarks" / "suite.json").read_text())
    assert len(suite["cases"]) == 19
    assert sum(len(c["faults"]) for c in suite["cases"]) == 13
    assert sum(not c["faults"] for c in suite["cases"]) == 7
    assert set(suite["faults"]) == {f for c in suite["cases"] for f in c["faults"]}
    for case in suite["cases"]:
        assert (ROOT / "examples" / case["example"] / "ofcdc.yaml").is_file()
        for fault_id in case["faults"]:
            fault = suite["faults"][fault_id]
            assert fault["ofcdc"]["status"] == "cex"
            assert {"ofcdc", "jasper"} <= set(fault)


def test_parameterized_rtl_is_shared_by_tools(tmp_path):
    run = load_module("run")
    case = {"id": "gray_sync/binary", "example": "gray_sync", "variant": "binary"}
    rtl, params = run.prepare_rtl(case, tmp_path)
    text = rtl.read_text()
    assert params == {"MODE": 1}
    assert text.count("parameter int MODE = 1") == 2
    assert "parameter int MODE = 0" not in text


def test_jasper_script_without_resets(tmp_path):
    run = load_module("run")
    from open_formal_cdc.config import parse_config
    cfg = parse_config({"design": {"top": "t", "files": ["t.sv"]},
                        "clocks": [{"name": "a", "port": "clk"}]}, tmp_path / "c.yaml")
    script = run.jasper_script(cfg, tmp_path / "t.sv")
    assert not any(line.startswith("reset ") for line in script.splitlines())


def test_report_parsers(tmp_path):
    run = load_module("run")
    (tmp_path / "summary.rpt").write_text(
        "[1] CDC_u_sync.q_bus_gray_coded cex B 3 0,010 s\n"
        "[2] CDC_u_sync.q_data_stable proven B 0,010 s\n")
    (tmp_path / "violations.csv").write_text("Violation Type,Check\nFunctional,bus_gray_coded\n")
    parsed = run.parse_jasper(tmp_path, 0)
    assert [p["status"] for p in parsed["properties"]] == ["cex", "proven"]
    assert parsed["violations"][0]["Check"] == "bus_gray_coded"



def test_gray_scoring_in_both_tools():
    score = load_module("score")
    suite = json.loads((ROOT / "benchmarks" / "suite.json").read_text())
    fault = suite["faults"]["GRAY-BINARY"]
    assert score.ofcdc_evidence({}, fault, {"results": [{"check": "gray_u_tx_ptr", "status": "cex"}]})
    assert score.jasper_evidence(fault["jasper"], {"properties": [{"name": "CDC_q_bus_gray_coded",
                                                                    "status": "cex"}]})


def test_paired_rtl_and_m4_ablation(tmp_path):
    run = load_module("run")
    score = load_module("score")
    suite = json.loads((ROOT / "benchmarks" / "suite.json").read_text())
    case = next(c for c in suite["cases"] if c["id"] == "glitch_conv/paired")
    assert case["faults"] == ["CONV-PAIRED"]
    assert suite["faults"]["CONV-PAIRED"]["claim"] == "sufficient_condition"
    rtl, params = run.prepare_rtl(case, tmp_path)
    assert params == {"BIN": 2} and "parameter int BIN = 2" in rtl.read_text()
    raw = {"results": [{"check": "glitch_u_and_s1", "template": "onechange", "status": "cex"},
                       {"check": "hazard_u_and_s1", "template": "nohazard", "status": "proven"}]}
    assert score.ofcdc_m4_ablation(raw) == {"onechange": "cex", "nohazard": "proven",
                                            "reading": "discharged"}
    raw["results"][1]["status"] = "cex"
    assert score.ofcdc_m4_ablation(raw)["reading"] == "hazard_candidate"
    assert score.commercial_glitch_evidence("jasper", {"properties": [
        {"name": "CDC_u_and.q_data_stable", "status": "cex"}]}) == ["CDC_u_and.q_data_stable:cex"]


def test_m4_ablation_must_be_stable(tmp_path, monkeypatch):
    score = load_module("score")
    monkeypatch.setattr(score, "ROOT", tmp_path)
    monkeypatch.setattr(score, "RESULTS", tmp_path)
    out = tmp_path / "glitch_conv__paired"
    out.mkdir()
    runs = []
    for nohazard in ("proven", "cex"):
        raw = {"results": [{"check": "glitch_u_and_s1", "template": "onechange", "status": "cex"},
                           {"check": "hazard_u_and_s1", "template": "nohazard", "status": nohazard},
                           {"check": "conv_st_b", "template": "onechange", "status": "cex"}]}
        runs.append({"raw": raw})
    (out / "ofcdc.json").write_text(json.dumps({"status": "completed", "seconds": 1, "runs": runs}))
    summary = score.score_all(allow_partial=True)
    case = next(c for c in summary["cases"] if c["case"] == "glitch_conv/paired")
    assert case["m4_ablation"]["reading"] == "unstable"
