# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""M5 on sliced vector flops in the scalable public CDC array."""

import dataclasses
import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_large_sliced_flops():
    path = Path(__file__).parents[2] / "benchmarks" / "synthetic" / "ofcdc.yaml"
    cfg = load_config(path)
    cfg.variants = [next(v for v in cfg.variants if v.name == "small")]
    cfg.options = dataclasses.replace(cfg.options, m5_checks=True)
    out = path.parent / "build" / "m5_small"
    result = run(cfg, out, make_executor(EXECUTOR), parallel=4, log=lambda _: None)
    assert result.mismatches == 0
    assert len(result.structures["small"].m5_targets) == 8
    expected = {f"m5_data_b_{hi}_{lo}" for hi, lo in ((7, 0), (15, 8), (23, 16), (31, 24))}
    expected |= {f"m5_flag_b_{i}" for i in range(4)}
    for check in expected:
        outcome = next(o for o in result.outcomes if o.check == check)
        assert outcome.template == "settled" and outcome.status == "proven"
    assert not any(o.check == "m5_conv_flag_b" for o in result.outcomes)
    convergence = next(o for o in result.outcomes if o.check == "m5_conv_data_b")
    assert convergence.status == "cex"
    log = (out / "small" / "jobs" / "m5_conv_data_b" / "job_ticks_cover" / "logfile.txt").read_text()
    for k in range(4):
        for name in (f"c_m5_first{k}", f"c_m5_second{k}", f"c_m5_pending{k}"):
            assert any("Reached cover statement" in line and line.endswith(f": {name}")
                       for line in log.splitlines()), name
