# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Clock ratios, T-PULSE, variant options, latches and synchronizer cells."""

import json
from pathlib import Path

import pytest

from open_formal_cdc.config import ConfigError, Clock, Input, parse_config, variant_config
from open_formal_cdc.jobs import build_job, ratio_bounds
from open_formal_cdc.netlist import Netlist
from open_formal_cdc.structural import Graph, analyze

DATA = Path(__file__).parent / "data"


def test_ratio_bounds():
    assert ratio_bounds(4, 10) == (2, 3)
    assert ratio_bounds(5, 10) == (2, 2)
    assert ratio_bounds(10, 10) == (1, 1)
    assert ratio_bounds(8, 10) == (1, 2)


RAW = {
    "design": {"top": "top", "files": ["t.sv"]},
    "clocks": [{"name": "a", "port": "clk_a", "period": 4}, {"name": "b", "port": "clk_b", "period": 10}],
    "checks": [{"name": "p", "template": "pulse", "signal": "u.lvl", "clock": "b", "src_clock": "a"}],
    "options": {"time_models": ["ticks", "clk2ff"], "clock_ratio": "periods"},
    "variants": {"free": {"options": {"clock_ratio": "free"}}},
}
NL = {"modules": {"top": {"ports": {"clk_a": {"direction": "input", "bits": [2]},
                                    "clk_b": {"direction": "input", "bits": [3]}},
                          "netnames": {"u.lvl": {"bits": [4]}}}}}


def test_pulse_job_with_ratio(tmp_path):
    cfg = parse_config(RAW, tmp_path / "c.yaml")
    build_job(cfg, cfg.design, Netlist(NL, "top"), cfg.checks[0], ["t.sv"], tmp_path / "j", "../rtl")
    w = (tmp_path / "j" / "wrapper_ticks.v").read_text()
    assert "ofcdc_pulse #(.W(1), .N(2), .TICKS(OFCDC_TICKS))" in w
    assert ".edge_d(ofcdc_edge_b)" in w and "localparam OFCDC_TICKS = 1;" in w
    assert "assume (ofcdc_cnt_a_b_now >= 2 && ofcdc_cnt_a_b_now <= 3)" in w
    w2 = (tmp_path / "j" / "wrapper_clk2ff.v").read_text()
    assert "wire ofcdc_edge_a = clk_a & !ofcdc_clkq_a;" in w2 and "localparam OFCDC_TICKS = 0;" in w2


def test_variant_options(tmp_path):
    cfg = parse_config(RAW, tmp_path / "c.yaml")
    free = variant_config(cfg, cfg.variants[1])
    assert free.options.clock_ratio == "free" and cfg.options.clock_ratio == "periods"
    build_job(free, free.design, Netlist(NL, "top"), free.checks[0], ["t.sv"], tmp_path / "j", "../rtl")
    assert "ofcdc_cnt_a_b" not in (tmp_path / "j" / "wrapper_ticks.v").read_text()


def test_periods_required(tmp_path):
    raw = {**RAW, "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b", "period": 10}]}
    with pytest.raises(ConfigError, match="period"):
        parse_config(raw, tmp_path / "c.yaml")


def _cell(name, typ, conns, dirs, src="t.sv:5"):
    return name, {"type": typ, "parameters": {}, "connections": conns, "port_directions": dirs,
                  "attributes": {"src": src}}


def _ff(name, clk, d, q, line):
    return _cell(name, "$dff", {"CLK": [clk], "D": [d], "Q": [q]},
                 {"CLK": "input", "D": "input", "Q": "output"}, f"t.sv:{line}")


def test_latch_on_path():
    cells = dict([_ff("$driver$src", 2, 10, 11, 3),
                  _cell("lat", "$dlatch", {"EN": [12], "D": [11], "Q": [13]},
                        {"EN": "input", "D": "input", "Q": "output"}, "t.sv:7"),
                  _ff("$driver$dst", 3, 13, 14, 9)])
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "cb": {"direction": "input", "bits": [3]},
                                      "d": {"direction": "input", "bits": [10]},
                                      "en": {"direction": "input", "bits": [12]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca"), Clock("b", "cb")], [Input("d", "a")], set())
    (x,) = st.crossings
    assert x.logic == "latch" and x.latch == "lat" and x.latch_line == 7


def test_library_cell():
    cells = dict([_ff("$driver$flag_q", 2, 10, 11, 3),
                  _cell("u_sync", "xpm_cdc_single",
                        {"src_clk": [2], "src_in": [11], "dest_clk": [3], "dest_out": [12]},
                        {"src_clk": "input", "src_in": "input", "dest_clk": "input", "dest_out": "output"}),
                  _ff("$driver$flag_b", 3, 12, 13, 9)])
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "cb": {"direction": "input", "bits": [3]},
                                      "d": {"direction": "input", "bits": [10]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca"), Clock("b", "cb")], [Input("d", "a")], set())
    (x,) = st.crossings
    assert x.scheme == "user_cell" and x.cell == "u_sync" and x.dst == "u_sync.src_in"


FIFO_NL = {"modules": {"top": {"ports": {
    "wclk": {"direction": "input", "bits": [2]}, "rclk": {"direction": "input", "bits": [3]},
    "wrst_n": {"direction": "input", "bits": [4]}, "rrst_n": {"direction": "input", "bits": [5]},
    "winc": {"direction": "input", "bits": [6]}, "rinc": {"direction": "input", "bits": [7]},
    "wdata": {"direction": "input", "bits": [8, 9]}, "rdata": {"direction": "output", "bits": [10, 11]},
    "wfull": {"direction": "output", "bits": [12]}, "rempty": {"direction": "output", "bits": [13]}},
    "netnames": {}}}}
FIFO_RAW = {
    "design": {"top": "top", "files": ["t.sv"]},
    "clocks": [{"name": "w", "port": "wclk"}, {"name": "r", "port": "rclk"}],
    "resets": [{"port": "wrst_n", "clock": "w"}, {"port": "rrst_n", "clock": "r"}],
    "checks": [{"name": "f", "template": "fifo", "wr_clock": "w", "wr_en": "winc", "wr_full": "wfull",
                "wr_data": "wdata", "rd_clock": "r", "rd_en": "rinc", "rd_empty": "rempty",
                "rd_data": "rdata", "depth": 4}],
    "variants": {"rr": {"resets": {"rrst_n": {"mode": "free"}}}},
}


def test_fifo_job_and_reset_variant(tmp_path):
    cfg = parse_config(FIFO_RAW, tmp_path / "c.yaml")
    rr = variant_config(cfg, cfg.variants[1])
    assert [r.mode for r in rr.resets] == ["init", "free"] and [r.mode for r in cfg.resets] == ["init", "init"]
    job = build_job(rr, rr.design, Netlist(FIFO_NL, "top"), rr.checks[0], ["t.sv"], tmp_path / "j", "../rtl")
    w = (tmp_path / "j" / "wrapper_ticks.v").read_text()
    assert "ofcdc_fifo #(.DW(2), .DEPTH(4), .TICKS(OFCDC_TICKS))" in w
    assert ".rd_data(ofcdc_out_rdata)" in w and ".wr_full(ofcdc_out_wfull)" in w
    assert "input rstfree_rrst_n" in w
    assert "memory_map" in (tmp_path / "j" / "job.sby").read_text()
    assert job.instance.asserts[-1] == "chk_f.p_data"


def test_bad_reset_override(tmp_path):
    raw = {**FIFO_RAW, "variants": {"x": {"resets": {"nope": {"mode": "free"}}}}}
    with pytest.raises(ConfigError, match="unknown reset port"):
        parse_config(raw, tmp_path / "c.yaml")


def test_onechange_and_convergence_proposal():
    from open_formal_cdc.structural import to_config
    from open_formal_cdc.structural.analysis import StructCrossing, Structure
    xs = [StructCrossing("st->u_and.s1", "st", "a", "u_and.s1", "b", "a", "b", bits=[(0, 0), (1, 0)],
                         scheme="ndff", logic="combo", d_net="u_and.d", cone_inputs=["st"]),
          StructCrossing("st->u_s0.s1", "st", "a", "u_s0.s1", "b", "a", "b", bits=[(0, 0)], scheme="ndff"),
          StructCrossing("st->u_s1.s1", "st", "a", "u_s1.s1", "b", "a", "b", bits=[(1, 0)], scheme="ndff")]
    st = Structure({}, xs, [{"at": "st_b", "domain": "b", "src_domain": "a",
                             "crossings": ["st->u_s0.s1", "st->u_s1.s1"], "sources": ["st"]}], [], {})
    crossings, checks, _ = to_config(st, {"a", "b"})
    by = {c.name: c for c in checks}
    assert by["glitch_u_and_s1"].params == {"signals": ["st"], "clocks": ["a"]}
    # same sources but a different role (advisory convergence): two checks
    assert by["conv_st_b"].params["role"] == "convergence" and len(checks) == 2
    assert {x.name: x.checks for x in crossings}["st->u_s0.s1"] == ["conv_st_b"]

    refined_crossings, with_hazard, _ = to_config(st, {"a", "b"}, hazard_checks=True)
    hazard = next(c for c in with_hazard if c.template == "nohazard")
    assert hazard.name == "hazard_u_and_s1"
    assert hazard.params == {"d": "u_and.d", "inputs": ["st"], "clock": "b"}
    and_crossing = next(x for x in refined_crossings if x.name == "st->u_and.s1")
    assert and_crossing.checks == ["hazard_u_and_s1"]
    assert any(c.name == "glitch_u_and_s1" for c in with_hazard)
    xs[0].cone_inputs = []
    _, incomplete, _ = to_config(st, {"a", "b"}, hazard_checks=True)
    assert not any(c.template == "nohazard" for c in incomplete)
    xs[0].cone_inputs = ["st"]
    st.domains = {"st": "a", "aux": "a", "other": "b"}
    _, domain_checks, _ = to_config(st, {"a", "b"}, hazard_checks=True, hazard_domain_inputs=True)
    domain_hazard = next(c for c in domain_checks if c.template == "nohazard")
    assert domain_hazard.params["inputs"] == ["aux", "st"]
    xs.append(StructCrossing("mem->u_and.s1", "mem", "a", "u_and.s1", "b", None, "b",
                             scheme="ndff", logic="combo", d_net="u_and.d", cone_inputs=["mem"],
                             src_kind="mem"))
    st.mem_domains = {"mem.rdata": "a"}
    st.mem_read_outputs = {"mem": ["mem.rdata"]}
    _, mem_checks, _ = to_config(st, {"a", "b"}, hazard_checks=True, hazard_domain_inputs=True)
    mem_hazard = next(c for c in mem_checks if c.template == "nohazard")
    assert mem_hazard.params["inputs"] == ["aux", "mem.rdata", "st"]
    st.mem_domains["mem.rdata"] = "b"
    _, rejected, _ = to_config(st, {"a", "b"}, hazard_checks=True, hazard_domain_inputs=True)
    assert not any(c.template == "nohazard" for c in rejected)
    _, async_checks, _ = to_config(st, {"a", "b"}, hazard_checks=True,
                                    hazard_domain_inputs=True, hazard_async=True)
    assert any(c.template == "nohazard" for c in async_checks)


def test_rdc_capture_proposal():
    from open_formal_cdc.structural import to_config
    from open_formal_cdc.structural.analysis import StructCrossing, Structure
    x = StructCrossing("src->dst", "src", "a", "dst", "b", "a", "b", scheme="ndff",
                       src_reset="ra", dst_reset="rb", dst_valid="cap", dst_valid_active="low")
    st = Structure({}, [x], [], [], {})
    _, checks, _ = to_config(st, {"a", "b"}, rdc_checks=True)
    (check,) = checks
    assert check.template == "rdc_capture"
    assert check.params == {"src_reset": "ra", "reset_active": "low", "dst_reset": "rb",
                            "dst_reset_active": "low", "dst_valid": "cap", "valid_active": "low",
                            "dst_clock": "b", "release_cycles": 1}
    x.dst_reset = "ra"
    _, shared, _ = to_config(st, {"a", "b"}, rdc_checks=True)
    assert not shared


def test_same_clock_rdc_proposal():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _cell("$driver$src_q", "$adff", {"CLK": [2], "D": [5], "Q": [6], "ARST": [3]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:4"),
        _cell("$driver$dst_q", "$adff", {"CLK": [2], "D": [6], "Q": [7], "ARST": [4]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:7"),
    ])
    for cell in cells.values():
        cell["parameters"]["ARST_POLARITY"] = "1"
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "ra": {"direction": "input", "bits": [3]},
                                      "rb": {"direction": "input", "bits": [4]},
                                      "d": {"direction": "input", "bits": [5]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")], [Input("d", "a")], {"ra", "rb"})
    assert st.crossings == []
    (x,) = st.reset_crossings
    assert x.scheme == "reset_domain" and x.src == "src_q" and x.dst == "dst_q"
    assert (x.src_reset, x.src_reset_active) == ("ra", "high")
    assert (x.dst_reset, x.dst_reset_active) == ("rb", "high")
    assert to_config(st, {"a"}) == ([], [], [])
    crossings, checks, _ = to_config(st, {"a"}, rdc_checks=True)
    assert crossings[0].scheme == "reset_domain" and crossings[0].checks == [checks[0].name]
    assert checks[0].params["reset_active"] == "high" and checks[0].params["dst_reset"] == "rb"
    from open_formal_cdc.report import structure_text
    report = structure_text(st, checks, [])
    assert "Reset-domain crossings:" in report and "src_q->dst_q" in report
    assert "ra (high)" in report and "rb (high)" in report


def test_reset_signal_crossing_proposal():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _ff("$driver$r_q", 2, 4, 5, 4),
        _cell("$driver$q", "$adff", {"CLK": [3], "D": ["0"], "Q": [6], "ARST": [5]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:8"),
    ])
    cells["$driver$q"]["parameters"]["ARST_POLARITY"] = "1"
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "cb": {"direction": "input", "bits": [3]},
                                      "d": {"direction": "input", "bits": [4]}},
                            "cells": cells, "netnames": {}}}}
    clocks = [Clock("a", "ca"), Clock("b", "cb")]
    st = analyze(Graph.from_json(nl, "t"), clocks, [Input("d", "a")], set())
    (reset,) = st.reset_signals
    assert reset.src == "r_q" and reset.src_clock == "a" and reset.dst_clock == "b"
    assert reset.active == "high" and reset.consumers == ["q"] and reset.dst_line == 8
    crossings, checks, _ = to_config(st, {"a", "b"}, rdc_checks=True)
    (check,) = checks
    assert check.template == "reset_release"
    assert check.params == {"signal": "r_q", "clock": "b", "reset_active": "high"}
    assert crossings[0].scheme == "reset_domain" and crossings[0].checks == [check.name]
    st = analyze(Graph.from_json(nl, "t"), clocks, [Input("d", "a")], set(),
                 clock_domain={"a": "g", "b": "g"})
    assert not st.reset_signals


def test_clock_mux_proposal():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _cell("$mux$gclk", "$mux", {"A": [2], "B": [3], "S": [4], "Y": [5]},
              {"A": "input", "B": "input", "S": "input", "Y": "output"}, "t.sv:5"),
        _ff("$driver$q", 5, 6, 7, 8),
    ])
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "cb": {"direction": "input", "bits": [3]},
                                      "mode": {"direction": "input", "bits": [4]},
                                      "d": {"direction": "input", "bits": [6]}},
                            "cells": cells,
                            "netnames": {"gclk": {"bits": [5]},
                                         "mode": {"bits": [4], "attributes": {"cdc_static": "1"}}}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca"), Clock("b", "cb")], [Input("d", "a")], set())
    (mux,) = st.clock_muxes
    assert mux.output == "gclk" and mux.select == "mode" and mux.select_static
    assert mux.clocks == ["a", "b"] and mux.line == 5
    crossings, checks, assumptions = to_config(st, {"a", "b"}, clock_mux_checks=True)
    (check,) = checks
    assert check.template == "clock_mux"
    assert check.params == {"signal": "gclk", "min_steps": 2, "clocks": ["a", "b"]}
    assert crossings[0].scheme == "clock_mux" and crossings[0].assumptions == ["static_mode"]
    assert [(a.name, a.kind, a.params["signal"]) for a in assumptions] == [("static_mode", "static", "mode")]


def test_andor_clock_mux_protocol():
    from open_formal_cdc.structural import to_config
    g = Graph.from_json(json.loads((DATA / "clock_mux_andor.json").read_text()), "good_glitch_free_mux")
    st = analyze(g, [Clock("clk0", "clk0"), Clock("clk1", "clk1"), Clock("cs", "cs")],
                 [Input("sel_d", "cs")], {"rst0", "rst1"})
    (mux,) = st.clock_muxes
    assert mux.protocol == "andor" and mux.select_d == "sel_d"
    assert mux.on == "on" and mux.on0 == 1 and mux.on1 == 2
    crossings, checks, assumptions = to_config(st, {"clk0", "clk1", "cs"}, clock_mux_checks=True)
    (assumption,) = assumptions
    assert assumption.kind == "clock_select" and assumption.params["verify"] is False
    assert assumption.params["select_d"] == "sel_d" and assumption.params["select"] == "sel"
    assert assumption.params["on"] == "on" and assumption.params["on0"] == 1 and assumption.params["on1"] == 2
    clock_crossing = next(x for x in crossings if x.scheme == "clock_mux")
    assert clock_crossing.assumptions == [assumption.name]
    assert checks[0].template == "clock_mux"


def test_plain_mux_has_no_andor_protocol():
    from open_formal_cdc.structural import to_config
    g = Graph.from_json(json.loads((DATA / "clock_mux_runt.json").read_text()), "cdc010_leg_synced_select_runt")
    st = analyze(g, [Clock("clk0", "clk0"), Clock("clk1", "clk1"), Clock("cs", "cs")],
                 [Input("sel_d", "cs")], {"rst0", "rst1"})
    assert st.clock_muxes[0].protocol is None
    _, _, assumptions = to_config(st, {"clk0", "clk1", "cs"}, clock_mux_checks=True)
    assert not assumptions


def test_reset_polarity_declaration():
    cells = dict([_cell("$driver$q", "$adff", {"CLK": [2], "D": ["0"], "Q": [3], "ARST": [4]},
                        {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:5")])
    cells["$driver$q"]["parameters"].update({"ARST_POLARITY": "0", "ARST_VALUE": "0"})
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "rst_n": {"direction": "input", "bits": [4]}},
                            "cells": cells,
                            "netnames": {"rst_n": {"bits": [4], "attributes": {"reset_polarity": "high"}}}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")], [], {"rst_n"})
    (mismatch,) = st.reset_polarities
    assert mismatch.kind == "declaration" and mismatch.expected == "high" and mismatch.actual == "low"
    from open_formal_cdc.structural import to_config
    crossings, checks, _ = to_config(st, {"a"}, rdc_checks=True)
    assert not checks and "declaration reset polarity mismatch" in crossings[0].structural_error


def test_reset_polarity_producer():
    cells = dict([
        _cell("$driver$prod_q", "$adff", {"CLK": [2], "D": [5], "Q": [6], "ARST": [7]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:3"),
        _cell("$driver$q", "$adff", {"CLK": [2], "D": ["0"], "Q": [8], "ARST": [6]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:6"),
    ])
    cells["$driver$prod_q"]["parameters"].update({"ARST_POLARITY": "0", "ARST_VALUE": "0"})
    cells["$driver$q"]["parameters"].update({"ARST_POLARITY": "1", "ARST_VALUE": "0"})
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "d": {"direction": "input", "bits": [5]},
                                      "rst_n": {"direction": "input", "bits": [7]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")], [Input("d", "a")], {"rst_n"})
    (mismatch,) = st.reset_polarities
    assert mismatch.kind == "producer" and mismatch.expected == "high" and mismatch.actual == "low"
    from open_formal_cdc.structural import to_config
    _, checks, _ = to_config(st, {"a"}, rdc_checks=True)
    (check,) = [c for c in checks if c.template == "reset_value"]
    assert check.params == {"reset": "rst_n", "reset_active": "low", "dst": "q", "value": 0}


def test_sync_reset_mux_proposal():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _ff("$driver$src_q", 2, 4, 10, 3),
        _cell("$procmux$2", "$mux", {"A": [7], "B": ["0"], "S": [10], "Y": [9]},
              {"A": "input", "B": "input", "S": "input", "Y": "output"}, "t.sv:5"),
        _ff("$driver$q", 3, 9, 11, 6),
    ])
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "cb": {"direction": "input", "bits": [3]},
                                      "kill": {"direction": "input", "bits": [4]},
                                      "d": {"direction": "input", "bits": [7]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca"), Clock("b", "cb")],
                 [Input("kill", "a"), Input("d", "b")], set())
    (reset,) = st.reset_signals
    assert reset.src == "src_q" and reset.active == "high" and reset.sync
    assert reset.consumers == ["q"] and reset.dst_line == 6
    _, checks, _ = to_config(st, {"a", "b"}, rdc_checks=True)
    (check,) = [c for c in checks if c.template == "srst_release"]
    assert check.params == {"signal": "src_q", "clock": "b", "reset_active": "high"}


def test_reset_logic_proposal():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _ff("$driver$fa_q", 2, 4, 5, 2),
        _ff("$driver$fb_q", 2, 6, 7, 3),
        _cell("$and$rst", "$and", {"A": [5], "B": [7], "Y": [8]},
              {"A": "input", "B": "input", "Y": "output"}, "t.sv:4"),
        _cell("$driver$q", "$adff", {"CLK": [2], "D": [9], "Q": [10], "ARST": [8]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:7"),
    ])
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "a": {"direction": "input", "bits": [4]},
                                      "b": {"direction": "input", "bits": [6]},
                                      "d": {"direction": "input", "bits": [9]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")],
                 [Input("a", "a"), Input("b", "a"), Input("d", "a")], set())
    (logic,) = st.reset_logic
    assert logic.kind == "rdc004" and logic.sources == ["fa_q", "fb_q"] and logic.line == 7
    crossings, _, _ = to_config(st, {"a"}, rdc_checks=True)
    assert any(x.structural_error and "combinational reset logic" in x.structural_error
               for x in crossings)


def test_multi_source_reset_logic():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _cell("$or$rst", "$or", {"A": [4], "B": [5], "Y": [6]},
              {"A": "input", "B": "input", "Y": "output"}, "t.sv:4"),
        _cell("$driver$q", "$adff", {"CLK": [2], "D": [7], "Q": [8], "ARST": [6]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:6"),
    ])
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "a": {"direction": "input", "bits": [4]},
                                      "b": {"direction": "input", "bits": [5]},
                                      "d": {"direction": "input", "bits": [7]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")],
                 [Input("a", "a"), Input("b", "a"), Input("d", "a")], set())
    (logic,) = st.reset_logic
    assert logic.kind == "rdc005" and logic.sources == ["a", "b"]
    crossings, _, _ = to_config(st, {"a"}, rdc_checks=True)
    assert any(x.structural_error and "multiple independent reset sources" in x.structural_error
               for x in crossings)


def test_muxed_reset_logic():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _cell("$mux$rst", "$mux", {"A": [4], "B": [5], "S": [6], "Y": [7]},
              {"A": "input", "B": "input", "S": "input", "Y": "output"}, "t.sv:4"),
        _cell("$driver$q", "$adff", {"CLK": [2], "D": [8], "Q": [9], "ARST": [7]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:6"),
    ])
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "ra": {"direction": "input", "bits": [4]},
                                      "rb": {"direction": "input", "bits": [5]},
                                      "sel": {"direction": "input", "bits": [6]},
                                      "d": {"direction": "input", "bits": [8]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")],
                 [Input("ra", "a"), Input("rb", "a"), Input("sel", "a"), Input("d", "a")], set())
    (logic,) = st.reset_logic
    assert logic.kind == "rdc006" and logic.sources == ["ra", "rb", "sel"]
    crossings, _, _ = to_config(st, {"a"}, rdc_checks=True)
    assert any(x.structural_error and "muxed reset source" in x.structural_error
               for x in crossings)


def test_stuck_reset_chain():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _cell("$driver$head_q", "$adff", {"CLK": [2], "D": ["0"], "Q": [3], "ARST": [4]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:3"),
        _cell("$driver$q", "$adff", {"CLK": [2], "D": [5], "Q": [6], "ARST": [3]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:6"),
    ])
    for cell in cells.values():
        cell["parameters"].update({"ARST_POLARITY": "0", "ARST_VALUE": "0"})
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "d": {"direction": "input", "bits": [5]},
                                      "rst_n": {"direction": "input", "bits": [4]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")], [Input("d", "a")], {"rst_n"})
    (stuck,) = st.reset_stuck
    assert stuck.head == "head_q" and stuck.consumers == ["q"] and stuck.value == 0
    assert stuck.reset == "rst_n" and stuck.reset_active == "low"
    crossings, _, _ = to_config(st, {"a"}, rdc_checks=True)
    assert any(x.structural_error and "reset chain head" in x.structural_error
               for x in crossings)


def test_missing_reset_domain():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _cell("$driver$head", "$adff", {"CLK": [2], "D": ["1"], "Q": [4], "ARST": [3]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:3"),
        _cell("$driver$tail", "$adff", {"CLK": [2], "D": [4], "Q": [5], "ARST": [3]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:6"),
        _cell("$driver$qa", "$adff", {"CLK": [2], "D": [6], "Q": [7], "ARST": [5]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:9"),
        _cell("$driver$qb", "$adff", {"CLK": [8], "D": [9], "Q": [10], "ARST": [3]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:12"),
    ])
    for cell in cells.values():
        cell["parameters"].update({"ARST_POLARITY": "0", "ARST_VALUE": "0"})
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "cb": {"direction": "input", "bits": [8]},
                                      "d": {"direction": "input", "bits": [6]},
                                      "db": {"direction": "input", "bits": [9]},
                                      "rst_n": {"direction": "input", "bits": [3]}},
                            "cells": cells, "netnames": {}}}}
    clocks = [Clock("a", "ca"), Clock("b", "cb")]
    st = analyze(Graph.from_json(nl, "t"), clocks, [Input("d", "a"), Input("db", "b")], {"rst_n"})
    assert [(x.reset, x.clock, x.head, x.tail, x.consumers) for x in st.reset_chains] == \
        [("rst_n", "a", "head", "tail", ["qa"])]
    (miss,) = st.reset_domain_misses
    assert miss.missing == ["b"] and miss.chains == ["a"] and miss.consumers == ["qb"]
    crossings, _, _ = to_config(st, {"a", "b"}, rdc_checks=True)
    assert any(x.structural_error and "missing reset domain" in x.structural_error
               for x in crossings)


def test_reset_record_and_dual_use():
    from open_formal_cdc.structural import to_config
    cells = dict([
        _cell("$driver$head", "$adff", {"CLK": [2], "D": ["1"], "Q": [4], "ARST": [3]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:3"),
        _cell("$driver$tail", "$adff", {"CLK": [2], "D": [4], "Q": [5], "ARST": [3]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:6"),
        _cell("$driver$async_q", "$adff", {"CLK": [2], "D": [6], "Q": [7], "ARST": [5]},
              {"CLK": "input", "D": "input", "Q": "output", "ARST": "input"}, "t.sv:9"),
        _cell("$procmux$rst", "$mux", {"A": [6], "B": ["0"], "S": [5], "Y": [9]},
              {"A": "input", "B": "input", "S": "input", "Y": "output"}, "t.sv:11"),
        _ff("$driver$sync_q", 2, 9, 8, 12),
    ])
    for cell in cells.values():
        if cell["type"] == "$adff":
            cell["parameters"].update({"ARST_POLARITY": "0", "ARST_VALUE": "0"})
    nl = {"modules": {"t": {"ports": {"ca": {"direction": "input", "bits": [2]},
                                      "d": {"direction": "input", "bits": [6]},
                                      "rst_n": {"direction": "input", "bits": [3]}},
                            "cells": cells, "netnames": {}}}}
    st = analyze(Graph.from_json(nl, "t"), [Clock("a", "ca")], [Input("d", "a")], {"rst_n"})
    (dual,) = st.reset_dual_uses
    assert dual.src == "tail" and dual.async_user == "async_q" and dual.sync_users == ["sync_q"]
    crossings, _, _ = to_config(st, {"a"}, rdc_checks=True)
    assert any(x.structural_note and "reset chain head->tail" in x.structural_note
               for x in crossings)
    assert any(x.structural_error and "asynchronous and synchronous consumers" in x.structural_error
               for x in crossings)
