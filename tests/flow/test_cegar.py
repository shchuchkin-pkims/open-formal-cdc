# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""End-to-end abstraction refinement with real SBY proofs."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.cegar import cegar
from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_spurious_and_confirmed_counterexamples():
    path = Path(__file__).parents[2] / "experiments" / "e_cegar" / "ofcdc.yaml"
    cfg = load_config(path)
    cfg.variants = [v for v in cfg.variants if v.name in ("good", "bad")]
    reports = cegar(cfg, path.parent / "build" / "pytest", make_executor(EXECUTOR),
                    only=["stable"], max_rounds=1, log=lambda _: None)
    by_variant = {r.variant: r for r in reports}
    assert by_variant["good"].status == "proven"
    assert by_variant["good"].abstract_cex == "discharged"
    assert by_variant["bad"].status == "cex"
    assert by_variant["bad"].abstract_cex == "confirmed"
    assert by_variant["good"].cut_evidence == {"dst_data_q": "discharges"}
    assert by_variant["bad"].cut_evidence == {"dst_data_q": "not_required"}
    assert set(by_variant["good"].rounds[0].proof.values()) == {"FAIL"}
    assert set(by_variant["good"].rounds[-1].proof.values()) == {"PASS"}
    assert set(by_variant["bad"].rounds[-1].proof.values()) == {"FAIL"}
    for result in reports:
        assert result.rounds[0].status == "cex" and result.rounds[0].trace
        assert result.rounds[-1].cuts == []
        assert all(status in ("cex", "proven") for status in result.rounds[-1].models.values())
    assert (path.parent / "build" / "pytest" / "cegar.json").exists()


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_automatic_en_stable_focus():
    path = Path(__file__).parents[2] / "experiments" / "e_cegar" / "ofcdc.yaml"
    cfg = load_config(path)
    cfg.variants = [v for v in cfg.variants if v.name == "good"]
    cfg.checks[0].params.pop("cut")
    cfg.checks[0].params.pop("cut_mode")
    logs = []
    reports = cegar(cfg, path.parent / "build" / "pytest_auto", make_executor(EXECUTOR),
                    only=["stable"], max_rounds=1, log=logs.append)
    assert logs.count("[1/3] reading the design (1 variant(s))") == 1
    assert logs.count("[1/3] reusing the design netlist (1 variant(s))") == 2
    (result,) = reports
    assert result.status == "proven" and result.abstract_cex == "discharged"
    assert result.cut_evidence == {"dst_data_q": "discharges"}
    assert result.rounds[0].cuts == ["dst_data_q"]
    assert (path.parent / "build" / "pytest_auto" / "good" / "focus.json").exists()
