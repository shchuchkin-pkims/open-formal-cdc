# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
import pytest

from open_formal_cdc.cegar import _final_status
from open_formal_cdc.config import parse_config
from open_formal_cdc.flow import CheckOutcome, FlowError, RunResult, _reuse_frontend
from open_formal_cdc.results import ModelResult


def result(status):
    outcome = CheckOutcome("base", "stable", "en_stable", status, None,
                           [ModelResult("ticks", status)])
    return RunResult([outcome], [], {})


def proof(out, status):
    path = out / "base" / "jobs" / "stable" / "job_ticks_prove"
    path.mkdir(parents=True)
    (path / "status").write_text(status + "\n")


def test_full_proof_with_unresolved_cover_is_not_proven(tmp_path):
    proof(tmp_path, "PASS")
    status, cex_state, _, detail = _final_status(tmp_path, result("unknown"), "stable", True, False)
    assert status == "unknown" and cex_state == "discharged"
    assert "covers are unresolved" in detail


def test_full_counterexample_cannot_contradict_abstract_proof(tmp_path):
    proof(tmp_path, "FAIL")
    status, _, _, detail = _final_status(tmp_path, result("cex"), "stable", False, True)
    assert status == "error" and "contradicts" in detail


def test_reused_frontend_must_match(tmp_path):
    (tmp_path / "t.sv").write_text("module t; endmodule\n")
    cfg = parse_config({"design": {"top": "t", "files": ["t.sv"]},
                        "clocks": [{"name": "a", "port": "clk"}]}, tmp_path / "c.yaml")
    reference = tmp_path / "reference" / "base" / "frontend"
    reference.mkdir(parents=True)
    (reference / "frontend.ys").write_text("different script\n")
    with pytest.raises(FlowError, match="does not match"):
        _reuse_frontend(cfg, reference, tmp_path / "out", log=lambda _: None)
