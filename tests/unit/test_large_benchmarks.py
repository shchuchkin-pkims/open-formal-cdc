# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Tests for large synthetic and real-IP benchmark setup."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def load_large_runner():
    spec = importlib.util.spec_from_file_location("large_run", ROOT / "benchmarks" / "large" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_large_suite_paths():
    suite = json.loads((ROOT / "benchmarks" / "large" / "suite.json").read_text())
    assert len(suite["cases"]) == 7
    for case in suite["cases"]:
        assert (ROOT / case["config"]).is_file()


def test_real_ip_options_reach_commercial_scripts(tmp_path):
    run = load_large_runner()
    case = {"id": "riscv_dmi/base", "config": "benchmarks/real_ip/riscv_dmi/ofcdc.yaml", "variant": "base"}
    cfg, _, _ = run.load_case(case)
    files, filelist = run.prepare_sources(case, tmp_path)
    jasper = run.jasper_script(cfg, files)
    assert "+incdir+" in jasper and "+define+VERILATOR" in jasper
    assert "elaborate -top dmi_jtag" in jasper


def test_engine_override(tmp_path, monkeypatch):
    run = load_large_runner()
    case = {"id": "cdc_array/small", "config": "benchmarks/synthetic/ofcdc.yaml", "variant": "small"}
    cfg, _, _ = run.load_case(case)
    monkeypatch.setenv("OFCDC_PROVE_ENGINE", "aiger rIC3")
    run.apply_engine_override(cfg)
    assert cfg.options.prove_engine == "aiger rIC3"


def test_synthetic_large_parameters(tmp_path):
    run = load_large_runner()
    case = {"id": "cdc_array/large", "config": "benchmarks/synthetic/ofcdc.yaml", "variant": "large"}
    files, filelist = run.prepare_sources(case, tmp_path)
    text = files[0].read_text()
    assert "parameter int N = 64" in text
    assert "parameter int BUG = 0" in text
    assert filelist.read_text().strip() == str(files[0])


def test_large_fault_scoring_and_deduplication():
    spec = importlib.util.spec_from_file_location("large_report", ROOT / "benchmarks" / "large" / "report.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    assert report.detect("cdc_array/binary", "ofcdc", {"results": [{"check": "gray_ptr_a_7_0", "status": "cex"}]}) == "1/1"
    jasper_raw = {"properties": [{"name": "CDC_q_bus_gray_coded", "status": "cex"}]}
    assert report.detect("cdc_array/binary", "jasper", jasper_raw) == "1/1"
    assert report.detect("cdc_array/binary", "jasper", jasper_raw, jasper_raw) == "0/1 (base also cex)"
    assert report.detect("cdc_array/missing_stage", "jasper", {"violations": [{"Check": "no_scheme"}]}) == "1/1"
