# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from pathlib import Path

import pytest

from open_formal_cdc.config import ConfigError, parse_config, variant_design

BASE = {
    "design": {"top": "t", "files": ["t.sv"], "params": {"P": 0}},
    "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b"}],
    "resets": [{"port": "rst_n", "clock": "a"}],
    "inputs": [{"port": "x", "clock": "a"}, {"port": "y"}],
    "checks": [{"name": "c1", "template": "gray", "signal": "s", "clock": "a", "expect": "proven"}],
    "variants": {"bad": {"params": {"P": 1}, "expect": {"c1": "cex"}}},
}


def cfg(**over):
    raw = {**BASE, **over}
    return parse_config(raw, Path("/tmp/x/ofcdc.yaml"))


def test_parse_basic():
    c = cfg()
    assert c.design.files == [Path("/tmp/x/t.sv")]
    assert c.clock("b").port == "b"
    assert c.reset_of("a").active_low
    assert c.reset_of("b") is None
    assert c.checks[0].params == {"signal": "s", "clock": "a"}
    assert [v.name for v in c.variants] == ["base", "bad"]
    assert c.variants[1].expect == {"c1": "cex"}
    assert variant_design(c, c.variants[1]).params == {"P": 1}
    assert c.design.params == {"P": 0}


@pytest.mark.parametrize("over,msg", [
    ({"clocks": []}, "at least one clock"),
    ({"resets": [{"port": "r", "clock": "zz"}]}, "unknown clock"),
    ({"inputs": [{"port": "x", "clock": "zz"}]}, "unknown clock"),
    ({"checks": [{"name": "c", "template": "gray", "expect": "maybe"}]}, "expect"),
    ({"options": {"time_models": ["warp"]}}, "time_models"),
    ({"variants": {"v": {"expect": {"nope": "cex"}}}, "options": {"structural": False}}, "unknown check"),
])
def test_errors(over, msg):
    with pytest.raises(ConfigError, match=msg):
        cfg(**over)


def test_base_variant_extends():
    c = cfg(variants={"base": {"expect": {"x->y": "safe"}}, "bad": {"params": {"P": 1}}})
    assert [v.name for v in c.variants] == ["base", "bad"]
    assert c.variants[0].expect == {"c1": "proven", "x->y": "safe"}


def test_filelist_incdir_and_define(tmp_path):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "t.sv").write_text("module t; endmodule\n")
    (tmp_path / "rtl.f").write_text("+incdir+inc+inc2\n+define+VERILATOR+FOO=1\nrtl/t.sv\n")
    c = parse_config({"design": {"top": "t", "filelist": "rtl.f"},
                      "clocks": [{"name": "a", "port": "clk"}]}, tmp_path / "ofcdc.yaml")
    assert c.design.files == [(tmp_path / "rtl" / "t.sv").resolve()]
    assert c.design.slang_args == [f"-I{(tmp_path / 'inc').resolve()}",
                                   f"-I{(tmp_path / 'inc2').resolve()}", "-DVERILATOR", "-DFOO=1"]
