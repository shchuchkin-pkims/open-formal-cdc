# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from types import SimpleNamespace

from open_formal_cdc.ablate import ablate
from open_formal_cdc.config import parse_config
from open_formal_cdc.flow import CheckOutcome


def test_assumption_ablation_classifies_help_and_redundancy(tmp_path, monkeypatch):
    cfg = parse_config({
        "design": {"top": "top", "files": ["t.sv"]},
        "clocks": [{"name": "a", "port": "clk_a"}],
        "checks": [{"name": "g", "template": "gray", "signal": "q", "clock": "a"}],
        "assumptions": [
            {"name": "needed", "kind": "constant", "signal": "go", "value": 0},
            {"name": "extra", "kind": "constant", "signal": "go", "value": 1},
        ],
        "options": {"structural": False},
    }, tmp_path / "c.yaml")

    def fake_run(c, out, executor, parallel, only, log):
        status = "cex" if not any(a.name == "needed" for a in c.assumptions) else "proven"
        return SimpleNamespace(outcomes=[CheckOutcome("base", "g", "gray", status, None)], verdicts=[])

    monkeypatch.setattr("open_formal_cdc.ablate.run", fake_run)
    effects = ablate(cfg, tmp_path, executor=None)
    assert [e.classification for e in effects] == ["helps", "redundant"]
    assert (tmp_path / "ablation.json").is_file()
