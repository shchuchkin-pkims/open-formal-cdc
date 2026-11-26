# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Automatic next-state focus for a Gray-code property."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.cegar import cegar
from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_gray_automatic_focus():
    path = Path(__file__).parents[2] / "experiments" / "e_cegar_gray" / "ofcdc.yaml"
    cfg = load_config(path)
    cfg.variants = [v for v in cfg.variants if v.name in ("good", "bad")]
    cfg.checks[0].params.pop("cut")
    cfg.checks[0].params.pop("cut_mode")
    reports = cegar(cfg, path.parent / "build" / "pytest", make_executor(EXECUTOR),
                    only=["gray_ptr"], max_rounds=1, log=lambda _: None)
    by_variant = {r.variant: r for r in reports}
    assert by_variant["good"].status == "proven"
    assert by_variant["good"].abstract_cex == "discharged"
    assert by_variant["good"].cut_evidence == {"aux_q": "discharges"}
    assert by_variant["bad"].status == "cex"
    assert by_variant["bad"].abstract_cex == "confirmed"
    assert by_variant["bad"].cut_evidence == {"aux_q": "not_required"}
    for result in reports:
        assert result.rounds[0].cuts == ["aux_q"]
        assert (path.parent / "build" / "pytest" / result.variant / "focus.json").exists()
