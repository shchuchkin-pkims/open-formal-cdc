# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""M7 asynchronous old/new input skew with no invented values."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m7_async_nonew():
    path = Path(__file__).parents[2] / "experiments" / "e_m7_async" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    for variant, expected in (("base", "proven"), ("binary", "cex"), ("step2", "cex")):
        plain = next(o for o in result.outcomes if o.variant == variant and o.check == "nonew_plain")
        skewed = next(o for o in result.outcomes if o.variant == variant and o.check == "nonew_async")
        assert plain.status == "proven"
        assert skewed.status == expected
        for model in cfg.options.time_models:
            log = (out / variant / "jobs" / "nonew_async" / f"job_{model}_cover" / "logfile.txt").read_text()
            assert any("Reached cover statement" in line and line.endswith(": c_skew0")
                       for line in log.splitlines())
