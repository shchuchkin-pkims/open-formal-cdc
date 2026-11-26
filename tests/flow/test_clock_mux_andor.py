# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Automatic AND/OR clock-mux protocol recognition and proof."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_clock_mux_andor():
    root = Path(__file__).parents[2] / "examples" / "clock_mux_andor"
    andor = run(load_config(root / "andor.yaml"), root / "build" / "andor",
                make_executor(EXECUTOR), log=lambda _: None)
    assert andor.mismatches == 0
    outcome = next(o for o in andor.outcomes if o.template == "clock_mux")
    assert outcome.status == "proven"
    assumption = andor.assumptions["base"][0]
    assert assumption.kind == "clock_select"
    assert assumption.params == {"select_d": "sel_d", "select": "sel", "on": "on",
                                 "on0": 1, "on1": 2, "verify": False}
    assert next(v for v in andor.verdicts if v.scheme == "clock_mux").verdict == "safe_assuming"

    runt = run(load_config(root / "runt.yaml"), root / "build" / "runt",
               make_executor(EXECUTOR), log=lambda _: None)
    assert runt.mismatches == 0
    outcome = next(o for o in runt.outcomes if o.template == "clock_mux")
    assert outcome.status == "cex"
    assert not runt.assumptions["base"]
    assert next(v for v in runt.verdicts if v.scheme == "clock_mux").verdict == "unsafe"
