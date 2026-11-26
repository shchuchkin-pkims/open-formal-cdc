# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""M5 same-domain propagation after a first-stage M2a injection."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_propagation_latency():
    path = Path(__file__).parents[2] / "experiments" / "e_m5_propagation" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    statuses = {o.check: o.status for o in result.outcomes}
    assert statuses == {
        "latency_plain": "proven",
        "latency_m2_limited": "cex",
        "latency_m2_allowed": "proven",
        "latency_m5_limited": "cex",
        "latency_m5_allowed": "proven",
        "settled_m5_limited": "cex",
    }
    for check in ("latency_m5_limited", "latency_m5_allowed", "settled_m5_limited"):
        for model in cfg.options.time_models:
            log = (out / "base" / "jobs" / check / f"job_{model}_cover" / "logfile.txt").read_text()
            for name in ("c_m5_first0", "c_m5_second0", "c_m5_pending0"):
                assert any("Reached cover statement" in line and line.endswith(f": {name}")
                           for line in log.splitlines()), (check, model, name)
