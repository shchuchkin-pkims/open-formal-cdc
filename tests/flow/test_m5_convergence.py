# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Functional no-new-values check at an M5 reconvergence point."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_reconvergence_nonew():
    path = Path(__file__).parents[2] / "experiments" / "e_m5_convergence" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    assert len(result.outcomes) == 8
    expected = {
        "base": {"conv_joined": "proven", "m5_conv_joined": "proven"},
        "paired": {"conv_joined": "cex", "m5_conv_joined": "cex"},
    }
    for variant, checks in expected.items():
        for check, status in checks.items():
            outcome = next(o for o in result.outcomes if o.variant == variant and o.check == check)
            assert outcome.status == status
        for check in ("m5_q0", "m5_q1"):
            assert next(o for o in result.outcomes
                        if o.variant == variant and o.check == check).status == "proven"
        for model in cfg.options.time_models:
            log = (out / variant / "jobs" / "m5_conv_joined" /
                   f"job_{model}_cover" / "logfile.txt").read_text()
            for name in ("c_m5_first0", "c_m5_second0", "c_m5_pending0",
                         "c_m5_first1", "c_m5_second1", "c_m5_pending1",
                         "chk_m5_conv_joined.c_new"):
                assert any("Reached cover statement" in line and line.endswith(f": {name}")
                           for line in log.splitlines()), (variant, model, name)
    verdicts = {v.variant: v.verdict for v in result.verdicts}
    assert verdicts == {"base": "safe", "paired": "unsafe"}
