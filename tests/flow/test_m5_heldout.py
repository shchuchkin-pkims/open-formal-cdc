# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Shared-source twin and triple M5 reconvergence."""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_m5_shared_source_reconvergence():
    path = Path(__file__).parents[2] / "experiments" / "e_m5_heldout" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    assert len(result.outcomes) == 11
    assert len([o for o in result.outcomes if o.variant == "base"]) == 2
    assert all(o.status == "proven" for o in result.outcomes if o.variant == "base")
    assert not any(o.variant == "base" and o.check == "m5_conv_joined" for o in result.outcomes)
    for variant, chains in (("twin", 2), ("triple", 3)):
        assert next(o for o in result.outcomes
                    if o.variant == variant and o.check == "conv_joined").status == "proven"
        for check in [f"m5_{name}2" for name in ("a", "b", "c")[:chains]]:
            assert next(o for o in result.outcomes
                        if o.variant == variant and o.check == check).status == "proven"
        convergence = next(o for o in result.outcomes
                           if o.variant == variant and o.check == "m5_conv_joined")
        assert convergence.status == "cex"
        for model in cfg.options.time_models:
            log = (out / variant / "jobs" / "m5_conv_joined" /
                   f"job_{model}_cover" / "logfile.txt").read_text()
            names = ["chk_m5_conv_joined.c_new"]
            for k in range(chains):
                names += [f"c_m5_first{k}", f"c_m5_second{k}", f"c_m5_pending{k}"]
            for name in names:
                assert any("Reached cover statement" in line and line.endswith(f": {name}")
                           for line in log.splitlines()), (variant, model, name)
