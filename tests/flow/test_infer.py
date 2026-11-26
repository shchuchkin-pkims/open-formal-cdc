# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Counterexample-driven assumption inference in two user-guided rounds."""

import os
from pathlib import Path

import pytest
import yaml

from open_formal_cdc.config import load_config, parse_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run
from open_formal_cdc.inference import infer

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")
ROOT = Path(__file__).parents[2]
HIGH = "always (!ack && req) -> next req"
LOW = "always (ack && !req) -> next !req"


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_infer_two_round_handshake():
    root = ROOT / "examples" / "infer_handshake"
    first = infer(load_config(root / "ofcdc.yaml"), root / "build" / "regression_first",
                  make_executor(EXECUTOR), parallel=8, only=["request_protocol"], max_limit=4,
                  log=lambda _: None)
    candidates = {c["expression"]: c for c in first[0]["candidates"]}
    assert candidates[HIGH]["status"] == "candidate" and candidates[HIGH]["quality"] > 0
    assert len(first[0]["traces"]) >= 2
    assert first[0]["implications"]
    exported = yaml.safe_load((root / "build" / "regression_first" / "assumptions.yaml").read_text())
    assert HIGH in [a["expression"] for a in exported["assumptions"]]
    assert all(a["quality"] > 0 and "implied_by" in a for a in exported["assumptions"])

    second = infer(load_config(root / "high_only.yaml"), root / "build" / "regression_second",
                   make_executor(EXECUTOR), parallel=8, only=["request_protocol"], max_limit=4,
                   log=lambda _: None)
    candidates = {c["expression"]: c for c in second[0]["candidates"]}
    assert candidates[LOW]["status"] == "candidate" and candidates[LOW]["quality"] > 0
    exported = yaml.safe_load((root / "build" / "regression_second" / "assumptions.yaml").read_text())
    assert LOW in [a["expression"] for a in exported["assumptions"]]

    constrained = run(load_config(root / "constrained.yaml"), root / "build" / "regression_constrained",
                      make_executor(EXECUTOR), log=lambda _: None)
    assert constrained.mismatches == 0
    assert len(constrained.outcomes) == 1
    assert [m.status for m in constrained.outcomes[0].models] == ["proven", "proven"]


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_infer_does_not_accept_vacuous_static_input(tmp_path):
    raw = {
        "design": {"top": "gray_sync", "files": [str(ROOT / "examples" / "gray_sync" / "gray_sync.sv")],
                   "params": {"MODE": 1}},
        "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b"}],
        "resets": [{"port": "rst_a_n", "active": "low", "clock": "a"},
                   {"port": "rst_b_n", "active": "low", "clock": "b"}],
        "inputs": [{"port": "inc", "clock": "a"}],
        "checks": [{"name": "gray_check", "template": "gray", "signal": "u_tx.ptr", "clock": "a"}],
        "options": {"time_models": ["ticks"], "structural": False, "timeout": 60},
    }
    cfg = parse_config(raw, tmp_path / "gray.yaml")
    report = infer(cfg, tmp_path / "infer", make_executor(EXECUTOR), parallel=4,
                   only=["gray_check"], max_limit=2, log=lambda _: None)
    candidates = {c["expression"]: c for c in report[0]["candidates"]}
    static = candidates["always !inc"]
    assert static["status"] == "unknown" and static["reason"] == "vacuity"
    assert static["quality"] is None and static["filters"]["assertion"] == "not_run"
    exported = yaml.safe_load((tmp_path / "infer" / "assumptions.yaml").read_text())
    assert "always !inc" not in [a["expression"] for a in exported["assumptions"]]
