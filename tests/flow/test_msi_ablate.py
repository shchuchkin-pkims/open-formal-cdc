# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-META with an independent MSI-free control run."""

import json
import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run
from open_formal_cdc.report import text

EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
def test_msi_ablation():
    path = Path(__file__).parents[2] / "examples" / "gray_sync" / "ofcdc.yaml"
    cfg = load_config(path)
    out = path.parent / "build" / "pytest_msi_ablate"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda _: None)
    assert result.mismatches == 0
    for variant, expected in (("base", "proven"), ("binary", "cex"), ("step2", "cex")):
        main = next(o for o in result.outcomes
                    if o.variant == variant and o.kind == "check" and o.check == "meta_u_tx_ptr")
        baseline = next(o for o in result.outcomes
                        if o.variant == variant and o.kind == "msi_baseline")
        assert main.status == expected
        assert baseline.status == "proven" and baseline.baseline_of == main.check
    report = text(result, cfg.options.time_models)
    assert "robust" in report and "sensitive" in report
    payload = json.loads((out / "results.json").read_text())
    controls = [r for r in payload["results"] if r["kind"] == "msi_baseline"]
    assert len(controls) == 3 and all(r["baseline_of"] == "meta_u_tx_ptr" for r in controls)
