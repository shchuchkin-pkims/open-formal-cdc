# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Structural analysis on saved Yosys netlists of the examples (no Yosys needed)."""

import json
from pathlib import Path

import pytest

from open_formal_cdc.config import Clock, Input
from open_formal_cdc.sdc import parse_sdc
from open_formal_cdc.structural import Graph, analyze, to_config

DATA = Path(__file__).parent / "data"
CLOCKS = [Clock("a", "clk_a"), Clock("b", "clk_b")]
RESETS = {"rst_a_n", "rst_b_n"}


def run(name, top, inputs, **kw):
    g = Graph.from_json(json.loads((DATA / f"{name}.json").read_text()), top)
    return analyze(g, CLOCKS, inputs, RESETS, **kw)


def test_ff_d_signal_slice():
    data = {"modules": {"top": {
        "cells": {"ff": {"type": "$dff", "parameters": {},
                         "connections": {"D": [12], "Q": [13]},
                         "port_directions": {"D": "input", "Q": "output"}},
                  "hidden": {"type": "$dff", "parameters": {},
                             "connections": {"D": [14], "Q": [15]},
                             "port_directions": {"D": "input", "Q": "output"}}},
        "ports": {}, "netnames": {"vec": {"bits": [10, 11, 12, 13], "hide_name": 0},
                                  "$mux$1": {"bits": [14], "hide_name": 1}}}}}
    g = Graph.from_json(data, "top")
    assert g.ff_d_signal(g.cells["ff"]) == "vec[2]"
    assert g.ff_d_signal(g.cells["hidden"]) == "$mux$1"


def test_gray_sync_bus():
    st = run("gray_sync", "gray_sync", [Input("inc", "a")])
    (x,) = st.crossings
    assert (x.src, x.dst, x.scheme) == ("u_tx.ptr", "u_sync.s1", "ndff_bus")
    assert x.stages == ["u_sync.s1", "u_sync.q"]
    assert len(x.bits) == 4 and x.logic == "direct" and x.src_width == 4
    crossings, checks, _ = to_config(st, {"a", "b"})
    assert [c.name for c in checks] == ["gray_u_tx_ptr"]
    assert checks[0].params == {"signal": "u_tx.ptr", "clock": "a"}
    assert crossings[0].checks == ["gray_u_tx_ptr"]


def test_handshake_mux():
    st = run("handshake_mux", "handshake_mux", [Input("go", "a"), Input("din", "a")])
    by = {x.name: x for x in st.crossings}
    assert by["u_tx.req->u_req_sync.s1"].scheme == "ndff"
    assert by["u_rx.ack->u_ack_sync.s1"].scheme == "ndff"
    data = by["u_tx.data->u_rx.data_out"]
    assert data.scheme == "mux_enable" and data.enable == "cap" and data.enable_active == "high"
    assert "u_req_sync.q" in data.notes[0]
    _, checks, _ = to_config(st, {"a", "b"})
    by_name = {c.name: c for c in checks}
    assert by_name["en_u_tx_data__u_rx_data_out"].params["enable"] == "cap"
    assert by_name["hs_u_tx_req"].params == {"req": "u_tx.req", "ack": "u_ack_sync.q", "clock": "a"}
    (h,) = st.handshakes
    assert h["data"] == ["u_tx.data->u_rx.data_out"]


def test_static_cfg_no_scheme():
    st = run("static_cfg", "static_cfg", [Input("wr", "a"), Input("wdata", "a")])
    (x,) = st.crossings
    assert (x.src, x.dst, x.scheme) == ("cfg", "q_b", "none")


def test_untyped_inputs_warn():
    st = run("static_cfg", "static_cfg", [])
    assert any("wr" in w for w in st.warnings)


def test_related_clocks_have_no_crossings():
    # one synchronous group: no crossings between a and b
    st = run("gray_sync", "gray_sync", [Input("inc", "a")], clock_domain={"a": "g", "b": "g"})
    assert st.crossings == []


def test_sdc_domain_map():
    s = parse_sdc("create_clock -name a -period 10 [get_ports clk_a]\n"
                  "create_clock -name b -period 7 [get_ports clk_b]\n")
    assert s.domain_map() == {"a": "sync0", "b": "sync0"}
    s = parse_sdc("create_clock -name a -period 10 [get_ports clk_a]\n"
                  "create_clock -name b -period 7 [get_ports clk_b]\n"
                  "set_clock_groups -asynchronous -group {a} -group {b}\n"
                  "set_input_delay -clock a 1.0 [get_ports {x y}]\n")
    assert s.domain_map() == {"a": "g0", "b": "g1"}
    assert s.input_clock == {"x": "a", "y": "a"}


def test_meta_check_with_msi(tmp_path):
    from open_formal_cdc.config import parse_config
    from open_formal_cdc.jobs import build_job
    from open_formal_cdc.netlist import Netlist
    st = run("gray_sync", "gray_sync", [Input("inc", "a")])
    (x,) = st.crossings
    assert x.stage_cell == "$driver$u_sync.s1" and x.d_net and x.d_width == 4
    _, checks, _ = to_config(st, {"a", "b"}, meta_checks=True)
    meta = next(c for c in checks if c.template == "nonew")
    assert meta.params["msi"][0]["cell"] == "$driver$u_sync.s1"
    data = json.loads((DATA / "gray_sync.json").read_text())
    cfg = parse_config({"design": {"top": "gray_sync", "files": ["g.sv"]},
                        "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b"}]},
                       tmp_path / "c.yaml")
    build_job(cfg, cfg.design, Netlist(data, "gray_sync"), meta, ["g.sv"], tmp_path / "j", "../rtl")
    sby = (tmp_path / "j" / "job.sby").read_text()
    assert "rename $driver$u_sync.s1 ofcdc_msi_ff0" in sby and "connect -port ofcdc_msi_ff0 D ofcdc_mi0" in sby
    w = (tmp_path / "j" / "wrapper_ticks.v").read_text()
    assert "ofcdc_msi_d #(.W(4), .TICKS(OFCDC_TICKS)) msi_0" in w and ".ofcdc_mi0(ofcdc_mi0)" in w


def test_m5_auto_proposal(tmp_path):
    from open_formal_cdc.config import parse_config
    from open_formal_cdc.jobs import build_job
    from open_formal_cdc.netlist import Netlist
    st = run("gray_sync", "gray_sync", [Input("inc", "a")])
    (x,) = st.crossings
    assert x.second_stage_cell == "$driver$u_sync.q"
    assert x.second_d_net == "u_sync.s1" and x.second_d_width == 4
    crossings, checks, _ = to_config(st, {"a", "b"}, m5_checks=True)
    m5 = next(c for c in checks if c.template == "settled")
    assert m5.name == "m5_u_sync_q" and m5.name in crossings[0].checks
    assert m5.params["data"] == "u_sync.s1" and m5.params["dst"] == "u_sync.q"
    assert m5.params["stable_edges"] == 2
    assert m5.params["m5"] == [{
        "first_cell": "$driver$u_sync.s1", "first_d": "u_sync.d",
        "second_cell": "$driver$u_sync.q", "second_d": "u_sync.s1", "width": 4, "clock": "b"}]
    data = json.loads((DATA / "gray_sync.json").read_text())
    cfg = parse_config({"design": {"top": "gray_sync", "files": ["g.sv"]},
                        "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b"}]},
                       tmp_path / "c.yaml")
    build_job(cfg, cfg.design, Netlist(data, "gray_sync"), m5, ["g.sv"], tmp_path / "j", "../rtl")
    sby = (tmp_path / "j" / "job.sby").read_text()
    assert "rename $driver$u_sync.s1 ofcdc_m5_first_ff0" in sby
    assert "rename $driver$u_sync.q ofcdc_m5_second_ff0" in sby
    w = (tmp_path / "j" / "wrapper_ticks.v").read_text()
    assert "ofcdc_settled #(.W(4), .STABLE_EDGES(2)) chk_m5_u_sync_q" in w
