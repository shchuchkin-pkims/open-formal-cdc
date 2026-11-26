# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""M5 for two synchronizer stages packed into one attributed vector flop."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_marked_vector_flop():
    path = Path(__file__).parents[2] / "experiments" / "e_m5_marked" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    assert len(result.outcomes) == 2
    for variant, stages in (("base", 2), ("three", 3)):
        check = "m5_q" if stages == 2 else "m5_sync_q_1"
        outcome = next(o for o in result.outcomes if o.variant == variant)
        assert outcome.check == check and outcome.status == "proven"
        target = result.structures[variant].m5_targets[0]
        assert target.first_cell == target.second_cell and target.cell_width == stages
        sby = (out / variant / "jobs" / check / "job.sby").read_text()
        assert f"add -input ofcdc_m5di0 {stages}" in sby
        assert "connect -port ofcdc_m5_first_ff0 D ofcdc_m5di0" in sby
        if stages == 3:
            assert "add -output ofcdc_m5full0 1" in sby
        for model in cfg.options.time_models:
            log = (out / variant / "jobs" / check / f"job_{model}_cover" / "logfile.txt").read_text()
            for name in ("c_m5_first0", "c_m5_second0", "c_m5_pending0", f"chk_{check}.c_settled"):
                assert any("Reached cover statement" in line and line.endswith(f": {name}")
                           for line in log.splitlines()), (variant, model, name)
    assert all(v.verdict == "safe" for v in result.verdicts)
