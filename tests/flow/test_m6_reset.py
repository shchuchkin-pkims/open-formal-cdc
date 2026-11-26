# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""M6 reset-release model with bounded deassertion latency."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m6_reset_latency():
    path = Path(__file__).parents[2] / "experiments" / "e_m6_reset" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    statuses = {o.check: o.status for o in result.outcomes}
    assert statuses == {"latency_base": "proven", "latency_msi_limited": "cex",
                        "latency_msi_allowed": "proven"}
    for check in ("latency_msi_limited", "latency_msi_allowed"):
        for model in cfg.options.time_models:
            log = (out / "base" / "jobs" / check / f"job_{model}_cover" / "logfile.txt").read_text()
            lines = log.splitlines()
            for name in ("c_msi_reset0", "c_msi_reset1",
                         "c_msi_reset_skip0", "c_msi_reset_skip1"):
                assert any("Reached cover statement" in line and line.endswith(f": {name}")
                           for line in lines), name
