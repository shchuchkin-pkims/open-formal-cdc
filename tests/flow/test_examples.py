# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""End-to-end runs of examples/ with Yosys and SBY.

Skipped unless OFCDC_EXECUTOR is set (for example ssh:user@host:~/.ssh/key).
"""

import os
from pathlib import Path

import pytest

from open_formal_cdc.config import load_config
from open_formal_cdc.executor import make_executor
from open_formal_cdc.flow import run

EXAMPLES = sorted((Path(__file__).parents[2] / "examples").glob("*/ofcdc.yaml"))
EXECUTOR = os.environ.get("OFCDC_EXECUTOR")


@pytest.mark.skipif(not EXECUTOR, reason="OFCDC_EXECUTOR not set")
@pytest.mark.parametrize("cfg_path", EXAMPLES, ids=lambda p: p.parent.name)
def test_example(cfg_path):
    cfg = load_config(cfg_path)
    out = cfg_path.parent / "build" / "pytest"
    result = run(cfg, out, make_executor(EXECUTOR), log=lambda s: None)
    bad = [(o.variant, o.check, o.status, o.expect) for o in result.outcomes if o.ok is False]
    bad += [(v.variant, v.crossing, v.verdict, v.expect) for v in result.verdicts if v.ok is False]
    assert not bad
