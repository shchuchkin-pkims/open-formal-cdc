# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Automatic M5 proposals for direct and logic-between-stages chains."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_auto_settled():
    path = Path(__file__).parents[2] / "experiments" / "e_m5_auto" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    assert len(result.outcomes) == 3
    for variant in ("base", "logic", "inline"):
        outcome = next(o for o in result.outcomes if o.variant == variant)
        assert outcome.check == "m5_sync_q" and outcome.template == "settled"
        assert outcome.status == "proven"
        crossing = result.structures[variant].crossings[0]
        assert crossing.second_stage_cell == "$driver$sync_q"
        assert crossing.second_d_net
        for model in cfg.options.time_models:
            log = (out / variant / "jobs" / "m5_sync_q" / f"job_{model}_cover" / "logfile.txt").read_text()
            for name in ("c_m5_first0", "c_m5_second0", "c_m5_pending0",
                         "chk_m5_sync_q.c_settled"):
                assert any("Reached cover statement" in line and line.endswith(f": {name}")
                           for line in log.splitlines()), (variant, model, name)
    assert result.structures["base"].crossings[0].logic == "direct"
    assert result.structures["logic"].crossings[0].logic == "between_stages"
    assert result.structures["inline"].crossings[0].logic == "between_stages"
    assert result.structures["inline"].crossings[0].second_d_net.startswith("$")
    assert not result.structures["enabled"].m5_targets
    assert not any(o.variant == "enabled" for o in result.outcomes)
