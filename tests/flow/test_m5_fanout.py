# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Independent M5 checks for fanout receivers without masking no_scheme."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_fanout_targets():
    path = Path(__file__).parents[2] / "experiments" / "e_m5_fanout" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    assert len(result.outcomes) == 5
    for variant in ("base", "logic"):
        crossing = result.structures[variant].crossings[0]
        assert crossing.scheme == "none"
        assert len(result.structures[variant].m5_targets) == 2
        verdict = next(v for v in result.verdicts if v.variant == variant)
        assert verdict.verdict == "no_scheme"
        for check in ("m5_q0", "m5_q1"):
            outcome = next(o for o in result.outcomes if o.variant == variant and o.check == check)
            assert outcome.status == "proven"
            for model in cfg.options.time_models:
                log = (out / variant / "jobs" / check / f"job_{model}_cover" / "logfile.txt").read_text()
                for name in ("c_m5_first0", "c_m5_second0", "c_m5_pending0",
                             f"chk_{check}.c_settled"):
                    assert any("Reached cover statement" in line and line.endswith(f": {name}")
                               for line in log.splitlines()), (variant, check, model, name)
    grouped = next(o for o in result.outcomes if o.variant == "grouped")
    assert grouped.check == "m5_group_b" and grouped.status == "proven"
    assert next(v for v in result.verdicts if v.variant == "grouped").verdict == "no_scheme"
    wrapper = (out / "grouped" / "jobs" / "m5_group_b" / "wrapper_ticks.v").read_text()
    assert "chk_m5_group_b_0" in wrapper and "chk_m5_group_b_1" in wrapper
    for model in cfg.options.time_models:
        log = (out / "grouped" / "jobs" / "m5_group_b" / f"job_{model}_cover" / "logfile.txt").read_text()
        for name in ("c_m5_first0", "c_m5_second0", "c_m5_pending0",
                     "c_m5_first1", "c_m5_second1", "c_m5_pending1",
                     "chk_m5_group_b_0.c_settled", "chk_m5_group_b_1.c_settled"):
            assert any("Reached cover statement" in line and line.endswith(f": {name}")
                       for line in log.splitlines()), (model, name)
