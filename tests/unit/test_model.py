# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from pathlib import Path

import pytest

from open_formal_cdc.config import ConfigError, Crossing, Endpoint, parse_config
from open_formal_cdc.model import assumption_states, crossing_verdict


def x(scheme="handshake", checks=(), assumptions=()):
    return Crossing("x", Endpoint("s", "a"), Endpoint("d", "b"), scheme, list(checks), list(assumptions))


def verdict(xing, check_status=None, check_assumes=None, states=None, twin_assumes=None):
    return crossing_verdict(xing, check_status or {}, check_assumes or {}, states or {}, twin_assumes or {})


def test_safe():
    assert verdict(x(checks=["c"]), {"c": "proven"})[0] == "safe"


def test_unsafe_wins():
    v, reasons, _ = verdict(x(checks=["c", "d"]), {"c": "cex", "d": "unknown"})
    assert v == "unsafe" and reasons == ["counterexample in c"]


def test_no_scheme_and_structural():
    assert verdict(x(scheme="none"))[0] == "no_scheme"
    assert verdict(x(scheme="ndff"))[0] == "structural"
    assert verdict(x(scheme="handshake"))[0] == "unresolved"


def test_assumption_chain():
    # check c assumes design assumption s; twin of s relies on environment assumption e
    args = dict(check_status={"c": "proven"}, check_assumes={"c": ["s"]}, twin_assumes={"s": ["e"]})
    v, reasons, deps = verdict(x(checks=["c"]), states={"s": "proven", "e": "environment"}, **args)
    assert v == "safe_assuming" and deps == ["s", "e"]
    v, reasons, _ = verdict(x(checks=["c"]), states={"s": "refuted", "e": "environment"}, **args)
    assert v == "unresolved" and "assumption s refuted" in reasons
    v, _, _ = verdict(x(checks=["c"]), states={"s": "unverified", "e": "environment"}, **args)
    assert v == "unresolved"


def test_static_scheme_by_assumption_only():
    v, _, _ = verdict(x(scheme="static", assumptions=["s"]), states={"s": "proven"})
    assert v == "safe"


def test_assumption_states():
    raw = {"design": {"top": "t", "files": ["t.sv"]}, "clocks": [{"name": "a"}],
           "assumptions": [{"name": "e", "kind": "constant", "signal": "i", "value": 0},
                           {"name": "s", "kind": "static", "signal": "r"},
                           {"name": "u", "kind": "static", "signal": "q"}]}
    cfg = parse_config(raw, Path("/tmp/c.yaml"))
    st = assumption_states(cfg.assumptions, {"e"}, {"s": "cex", "u": "unknown"})
    assert st == {"e": "environment", "s": "refuted", "u": "unverified"}


BASE = {"design": {"top": "t", "files": ["t.sv"]}, "clocks": [{"name": "a"}, {"name": "b"}],
        "checks": [{"name": "c", "template": "gray", "signal": "s", "clock": "a"}]}


@pytest.mark.parametrize("over,msg", [
    ({"assumptions": [{"name": "z", "kind": "magic", "signal": "s"}]}, "kind"),
    ({"assumptions": [{"name": "z", "kind": "static", "signal": "s", "applies_to": ["nope"]}]}, "applies_to"),
    ({"assumptions": [{"name": "c", "kind": "static", "signal": "s"}]}, "both as check and assumption"),
    ({"crossings": [{"name": "x", "from": {"signal": "s"}, "to": {"signal": "d"}, "scheme": "warp"}]}, "scheme"),
    ({"crossings": [{"name": "x", "from": {"signal": "s"}, "to": {"signal": "d"}, "checks": ["nope"]}]}, "unknown checks"),
    ({"crossings": [{"name": "x", "from": {"signal": "s"}, "to": {"signal": "d"}, "expect": "fine"}]}, "expect"),
])
def test_config_errors(over, msg):
    with pytest.raises(ConfigError, match=msg):
        parse_config({**BASE, **over}, Path("/tmp/c.yaml"))
