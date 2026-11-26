# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""M5 inside a declared synchronizer cell, including JSON reporting."""

import json
import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_inside_user_cell():
    path = Path(__file__).parents[2] / "experiments" / "e_m5_user_cell" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    assert len(result.verdicts) == 1 and result.verdicts[0].verdict == "safe"
    cell = result.cell_results["sync2"]
    assert len(cell.structures["base"].m5_targets) == 1
    outcome = next(o for o in cell.outcomes if o.check == "m5_q")
    assert outcome.template == "settled" and outcome.status == "proven"
    for model in cfg.options.time_models:
        log = (out / "cells" / "sync2" / "base" / "jobs" / "m5_q" /
               f"job_{model}_cover" / "logfile.txt").read_text()
        for name in ("c_m5_first0", "c_m5_second0", "c_m5_pending0", "chk_m5_q.c_settled"):
            assert any("Reached cover statement" in line and line.endswith(f": {name}")
                       for line in log.splitlines()), (model, name)
    payload = json.loads((out / "results.json").read_text())
    internal = payload["cells"]["sync2"]["results"]
    assert next(o for o in internal if o["check"] == "m5_q")["status"] == "proven"
