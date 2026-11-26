# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from pathlib import Path

import pytest

from open_formal_cdc.config import parse_config
from open_formal_cdc.jobs import build_job, vid
from open_formal_cdc.netlist import Netlist
from open_formal_cdc.templates import TemplateError

NETLIST = {"modules": {"top": {
    "ports": {
        "clk_a": {"direction": "input", "bits": [2]},
        "clk_b": {"direction": "input", "bits": [3]},
        "rst_n": {"direction": "input", "bits": [4]},
        "go": {"direction": "input", "bits": [5]},
        "async_in": {"direction": "input", "bits": [6]},
        "q": {"direction": "output", "bits": [7, 8]},
    },
    "netnames": {"u.ptr": {"bits": [9, 10, 11, 12]}, "u.en": {"bits": [13]}, "q": {"bits": [7, 8]}},
}}}


def make(tmp_path, check, models=("ticks", "clk2ff"), options=None):
    raw = {
        "design": {"top": "top", "files": ["t.sv"], "params": {"MODE": 1}},
        "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b"}],
        "resets": [{"port": "rst_n", "clock": "a"}],
        "inputs": [{"port": "go", "clock": "a"}],
        "checks": [check],
        "options": {"time_models": list(models), **(options or {})},
    }
    cfg = parse_config(raw, tmp_path / "ofcdc.yaml")
    nl = Netlist(NETLIST, "top")
    return build_job(cfg, cfg.design, nl, cfg.checks[0], ["t.sv"], tmp_path / "job", "../rtl")


def test_gray_job(tmp_path):
    job = make(tmp_path, {"name": "g", "template": "gray", "signal": "u.ptr", "clock": "a"})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert "read_slang t.sv --top top -G MODE=1" in sby
    assert "rename -output u.ptr ofcdc_s0" in sby
    assert "ticks_prove: formalff -declockgate" in sby
    assert "clk2ff_prove: multiclock on" in sby
    assert "ticks_prove: multiclock on" not in sby
    assert job.exposures == {"u.ptr": "ofcdc_s0"}
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "assume (tick_a | tick_b)" in w
    assert "always @* if (!gclk) ofcdc_en_a = tick_a;" in w
    assert "always @(posedge ofcdc_clk_a) ofcdc_in_go <= in_go;" in w     # synchronous input
    assert "wire ofcdc_in_async_in = in_async_in;" in w                  # asynchronous input
    assert ".rst_n(ofcdc_rstport_rst_n)" in w
    assert "ofcdc_gray #(.W(4)) chk_g (.clk(ofcdc_clk_a), .act(ofcdc_act_a), .v(ofcdc_s0));" in w
    w2 = (tmp_path / "job" / "wrapper_clk2ff.v").read_text()
    assert "$global_clock" in w2 and "gclk" not in w2


def test_port_signal_not_exposed(tmp_path):
    job = make(tmp_path, {"name": "g", "template": "gray", "signal": "q", "clock": "b"}, ["ticks"])
    assert job.exposures == {}
    assert "ofcdc_gray #(.W(2)) chk_g (.clk(ofcdc_clk_b), .act(ofcdc_act_b), .v(ofcdc_out_q));" in \
        (tmp_path / "job" / "wrapper_ticks.v").read_text()


def test_cut_job(tmp_path):
    make(tmp_path, {"name": "g", "template": "gray", "signal": "u.ptr", "clock": "a",
                    "cut": ["u.en"], "cut_mode": "state"})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert "abstract -state w:u.en" in sby
    with pytest.raises(ValueError, match="cannot be cut"):
        make(tmp_path, {"name": "g", "template": "gray", "signal": "u.ptr", "clock": "a",
                        "cut": ["clk_a"], "cut_mode": "state"})
    with pytest.raises(ValueError, match="cut_mode"):
        make(tmp_path, {"name": "g", "template": "gray", "signal": "u.ptr", "clock": "a",
                        "cut": ["u.en"], "cut_mode": "free"})


def test_rdc_capture_job(tmp_path):
    make(tmp_path, {"name": "r", "template": "rdc_capture", "src_reset": "rst_n",
                    "dst_valid": "go", "dst_clock": "b", "release_cycles": 2})
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_rdc_capture #(.RELEASE_CYCLES(2)) chk_r" in w
    assert ".src_rst_n(ofcdc_rstport_rst_n), .dst_valid(ofcdc_in_go));" in w
    assert ".act(ofcdc_act_b & ofcdc_init_done), .cap(ofcdc_edge_b & ofcdc_init_done)" in w
    make(tmp_path, {"name": "ra", "template": "rdc_capture", "src_reset": "u.en",
                    "reset_active": "high", "dst_reset": "rst_n", "dst_clock": "b"})
    active = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert ".act(ofcdc_init_done & ofcdc_rstport_rst_n)" in active
    assert ".src_rst_n(~ofcdc_s0)" in active
    with pytest.raises(TemplateError, match="positive"):
        make(tmp_path, {"name": "r0", "template": "rdc_capture", "src_reset": "rst_n",
                        "dst_valid": "go", "dst_clock": "b", "release_cycles": 0})


def test_reset_sync_job(tmp_path):
    make(tmp_path, {"name": "r", "template": "reset_sync", "signal": "q", "reset": "rst_n", "clock": "a"})
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_reset_sync #(.N(2)) chk_r (.clk(ofcdc_clk_a), .rst_n(ofcdc_rstport_rst_n), .v(ofcdc_out_q));" in w
    with pytest.raises(TemplateError, match="at least two"):
        make(tmp_path, {"name": "r1", "template": "reset_sync", "signal": "u.en", "reset": "rst_n", "clock": "a"})


def test_reset_release_job(tmp_path):
    make(tmp_path, {"name": "r", "template": "reset_release", "signal": "rst_n", "clock": "a"})
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_reset_release #(.ACTIVE_LOW(1)) chk_r" in w
    assert ".act(ofcdc_init_done), .cap(ofcdc_edge_a), .rst(ofcdc_rstport_rst_n));" in w
    make(tmp_path, {"name": "rh", "template": "reset_release", "signal": "u.en", "clock": "b",
                    "reset_active": "high"})
    high = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_reset_release #(.ACTIVE_LOW(0)) chk_rh" in high


def test_clock_mux_job(tmp_path):
    make(tmp_path, {"name": "cm", "template": "clock_mux", "signal": "u.en", "min_steps": 2,
                    "clocks": ["a", "b"]})
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_clock_mux #(.MIN_STEPS(2)) chk_cm" in w
    assert ".act(ofcdc_init_done), .v(ofcdc_s0));" in w
    assert "ofcdc_clock_leg #(.MIN_STEPS(2)) leg_0" in w
    assert "ofcdc_clock_leg #(.MIN_STEPS(2)) leg_1" in w
    with pytest.raises(TemplateError, match="at least 2"):
        make(tmp_path, {"name": "cm1", "template": "clock_mux", "signal": "u.en", "min_steps": 1})


def test_clock_select_assumption_job(tmp_path):
    make(tmp_path, {"name": "cs", "template": "env_clock_select", "select_d": "go", "select": "u.en",
                    "on": "q", "on0": 1, "on1": 2})
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_env_clock_select #(.W(2), .ON0(1), .ON1(2), .ASSERT(0), .INIT(0)) env_cs" in w
    assert ".sel_d(ofcdc_in_go), .sel(ofcdc_s0), .on(ofcdc_out_q));" in w


def test_reset_value_job(tmp_path):
    make(tmp_path, {"name": "rv", "template": "reset_value", "reset": "rst_n", "dst": "u.en", "value": 0})
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_reset_value #(.VALUE(0), .ACTIVE_LOW(1)) chk_rv" in w
    assert ".reset(ofcdc_rstport_rst_n), .dst(ofcdc_s0));" in w


def test_reset_latency_with_msi_reset(tmp_path):
    make(tmp_path, {"name": "rl", "template": "reset_latency", "src_reset": "rst_n", "tail_reset": "u.en",
                    "clock": "a", "max_cycles": 2,
                    "msi_reset": [{"cell": "$driver$u.en", "d": "rst_n", "port": "ARST", "active": "low"}]})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert "rename $driver$u.en ofcdc_msi_rst_ff0" in sby
    assert "connect -port ofcdc_msi_rst_ff0 ARST ofcdc_mri0" in sby
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_reset_latency #(.MAX_CYCLES(2), .ACTIVE_LOW(1)) chk_rl" in w
    assert "ofcdc_msi_reset #(.ACTIVE_LOW(1)) msi_reset_0" in w
    assert ".rst(ofcdc_mro0), .rst_seen(ofcdc_mri0), .msi_alt(ofcdc_msi_alt0), .msi_skip(ofcdc_msi_skip0));" in w
    assert "c_msi_reset_skip0: cover (ofcdc_msi_skip0);" in w
    assert "wire pick = $anyseq;" in (tmp_path / "job" / "ofcdc_msi_reset.v").read_text()


def test_async_nonew_skew_drives_receiver(tmp_path):
    make(tmp_path, {"name": "an", "template": "async_nonew", "src": "u.ptr[1:0]", "dst": "q",
                    "clock": "b",
                    "skew": [{"cell": "$driver$u.s1", "d": "u.d", "width": 4}]})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert "rename $driver$u.s1 ofcdc_skew_ff0" in sby
    assert "connect -set ofcdc_sko0 u.d" in sby
    assert "connect -port ofcdc_skew_ff0 D ofcdc_ski0" in sby
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_skew_cap #(.W(4)) skew_0 (.cap(ofcdc_edge_b & ofcdc_act_b)" in w
    assert ".d(ofcdc_sko0), .d_seen(ofcdc_ski0), .alt(ofcdc_skew_alt0));" in w
    assert ".src(ofcdc_s0[1:0]), .dst(ofcdc_out_q));" in w
    assert "c_skew0: cover (ofcdc_skew_alt0);" in w
    with pytest.raises(TemplateError, match="must list receiving stages"):
        make(tmp_path, {"name": "an0", "template": "async_nonew", "src": "u.ptr[1:0]", "dst": "q",
                        "clock": "b"})


def test_m5_propagation_drives_second_stage(tmp_path):
    make(tmp_path, {"name": "m5", "template": "rise_latency", "src": "go", "dst": "u.en",
                    "clock": "b", "max_cycles": 3,
                    "m5": [{"first_cell": "$driver$meta", "first_d": "u.en",
                            "second_cell": "$driver$sync", "second_d": "u.en", "width": 1}]})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert "rename $driver$meta ofcdc_m5_first_ff0" in sby
    assert "connect -port ofcdc_m5_first_ff0 D ofcdc_m5fi0" in sby
    assert "rename $driver$sync ofcdc_m5_second_ff0" in sby
    assert "connect -port ofcdc_m5_second_ff0 D ofcdc_m5si0" in sby
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_rise_latency #(.MAX_CYCLES(3)) chk_m5" in w
    assert "ofcdc_msi_d #(.W(1), .TICKS(OFCDC_TICKS)) m5_first_0" in w
    assert "ofcdc_msi_propagate #(.W(1), .TICKS(OFCDC_TICKS)) m5_second_0" in w
    assert ".cap(ofcdc_edge_b), .act(ofcdc_act_b), .trigger(ofcdc_m5fi0 ^ ofcdc_m5fo0)" in w
    assert "pending <= (pending | trigger) & ~propagate;" in \
        (tmp_path / "job" / "ofcdc_msi_propagate.v").read_text()
    assert "c_m5_second0: cover (ofcdc_m5_second_alt0);" in w
    with pytest.raises(TemplateError, match="must be positive"):
        make(tmp_path, {"name": "m50", "template": "rise_latency", "src": "go", "dst": "u.en",
                        "clock": "b", "max_cycles": 0})
    with pytest.raises(TemplateError, match="must be positive"):
        make(tmp_path, {"name": "st0", "template": "settled", "data": "u.en", "dst": "u.en",
                        "clock": "b", "stable_edges": 0})


def test_m5_shared_vector_cell(tmp_path):
    make(tmp_path, {"name": "m5s", "template": "settled", "data": "u.en", "dst": "u.en",
                    "clock": "b", "stable_edges": 2,
                    "m5": [{"first_cell": "$driver$same", "first_d": "u.en",
                            "second_cell": "$driver$same", "second_d": "u.en", "width": 1}]})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert sby.count("rename $driver$same ofcdc_m5_first_ff0") == 1
    assert "ofcdc_m5_second_ff0" not in sby
    assert "add -input ofcdc_m5di0 2" in sby
    assert "connect -port ofcdc_m5_first_ff0 D ofcdc_m5di0" in sby
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "assign ofcdc_m5di0 = {ofcdc_m5si0, ofcdc_m5fi0};" in w
    make(tmp_path, {"name": "m5s3", "template": "settled", "data": "u.en", "dst": "u.en",
                    "clock": "b", "stable_edges": 2,
                    "m5": [{"first_cell": "$driver$same", "first_d": "u.en",
                            "second_cell": "$driver$same", "second_d": "u.en", "width": 1,
                            "cell_width": 3, "remaining_d": "u.ptr"}]})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert "add -output ofcdc_m5full0 1" in sby and "add -input ofcdc_m5di0 3" in sby
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "assign ofcdc_m5di0 = {ofcdc_m5full0, ofcdc_m5si0, ofcdc_m5fi0};" in w


def test_m5_engine_overrides(tmp_path):
    options = {"m5_prove_engine": "aiger rIC3", "m5_cover_engine": "smtbmc boolector",
               "m5_cover_depth": 123}
    make(tmp_path, {"name": "m5e", "template": "settled", "data": "u.en", "dst": "u.en",
                    "clock": "b", "stable_edges": 2,
                    "m5": [{"first_cell": "$driver$meta", "first_d": "u.en",
                            "second_cell": "$driver$q", "second_d": "u.en", "width": 1}]}, options=options)
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert "ticks_cover: depth 123" in sby and "clk2ff_cover: depth 123" in sby
    assert "ticks_prove: aiger rIC3" in sby and "clk2ff_prove: aiger rIC3" in sby
    assert "ticks_cover: smtbmc boolector" in sby and "clk2ff_cover: smtbmc boolector" in sby
    options["m5_cover_depth"] = 0
    with pytest.raises(ValueError, match="m5_cover_depth"):
        make(tmp_path, {"name": "m5e0", "template": "settled", "data": "u.en", "dst": "u.en",
                        "clock": "b", "stable_edges": 2,
                        "m5": [{"first_cell": "$driver$meta", "first_d": "u.en",
                                "second_cell": "$driver$q", "second_d": "u.en", "width": 1}]}, options=options)


def test_nonew_vector_signals(tmp_path):
    make(tmp_path, {"name": "cn", "template": "nonew", "src": ["u.en", "go"],
                    "dst": ["u.en", "go"], "clocks": ["a", "b"]})
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "ofcdc_nonew #(.W(2)) chk_cn" in w
    assert ".src({ofcdc_s0, ofcdc_in_go}), .dst({ofcdc_s0, ofcdc_in_go}));" in w
    assert ".act(ofcdc_init_done & ofcdc_act_a & ofcdc_act_b)" in w
    with pytest.raises(TemplateError, match="must not be empty"):
        make(tmp_path, {"name": "cn0", "template": "nonew", "src": [], "dst": ["go"],
                        "clocks": ["b"]})


def test_settled_grouped_checks(tmp_path):
    make(tmp_path, {"name": "sg", "template": "settled", "data": ["u.en", "go"],
                    "dst": ["u.en", "go"], "clock": "b", "stable_edges": 2,
                    "m5": [{"first_cell": "$driver$meta", "first_d": "u.en",
                            "second_cell": "$driver$q0", "second_d": "u.en", "width": 1},
                           {"first_cell": "$driver$meta", "first_d": "u.en",
                            "second_cell": "$driver$q1", "second_d": "u.en", "width": 1}]})
    sby = (tmp_path / "job" / "job.sby").read_text()
    assert sby.count("rename $driver$meta ofcdc_m5_first_ff0") == 1
    assert "ofcdc_m5fo1" not in sby and "m5_first_1" not in sby
    w = (tmp_path / "job" / "wrapper_ticks.v").read_text()
    assert "m5_second_0" in w and "m5_second_1" in w
    assert "ofcdc_settled #(.W(1), .STABLE_EDGES(2)) chk_sg_0" in w
    assert "ofcdc_settled #(.W(1), .STABLE_EDGES(2)) chk_sg_1" in w
    with pytest.raises(TemplateError, match="equal nonzero length"):
        make(tmp_path, {"name": "sg0", "template": "settled", "data": ["u.en", "go"],
                        "dst": ["u.en"], "clock": "b", "stable_edges": 2})


def test_en_stable_width_check(tmp_path):
    with pytest.raises(TemplateError, match="1 bit"):
        make(tmp_path, {"name": "e", "template": "en_stable", "data": "u.en", "enable": "u.ptr",
                        "clock": "b"})


def test_unknown_net(tmp_path):
    with pytest.raises(KeyError, match="not found"):
        make(tmp_path, {"name": "g", "template": "gray", "signal": "u.nope", "clock": "a"})


def test_vid():
    assert vid("abc") == "abc"
    assert vid("u.x") == "\\u.x "


def test_assumptions_and_twin(tmp_path):
    from open_formal_cdc.config import Assumption
    from open_formal_cdc.jobs import is_environment, twin_check
    nl = Netlist(NETLIST, "top")
    env = Assumption("e", "constant", {"signal": "go", "value": 0})
    des = Assumption("s", "static", {"signal": "u.ptr"})
    assert is_environment(env, nl) and not is_environment(des, nl)
    job = make(tmp_path, {"name": "g", "template": "gray", "signal": "u.ptr", "clock": "a"})
    cfg_job_dir = tmp_path / "job2"
    raw_cfg = parse_config({"design": {"top": "top", "files": ["t.sv"]},
                            "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b"}],
                            "resets": [{"port": "rst_n", "clock": "a"}]}, tmp_path / "c.yaml")
    twin = build_job(raw_cfg, raw_cfg.design, nl, twin_check(des), ["t.sv"], cfg_job_dir, "../rtl",
                     [env], twin_of="s")
    w = (cfg_job_dir / "wrapper_ticks.v").read_text()
    assert "ofcdc_env_static #(.W(4), .ASSERT(1)) env_s (.act(ofcdc_init_done), .v(ofcdc_s0));" in w
    assert "ofcdc_env_constant #(.W(1), .ASSERT(0), .VALUE(1'd0)) env_e (.act(ofcdc_init_done), .v(ofcdc_in_go));" in w
    assert twin.assumes == ["e"] and twin.twin_of == "s"
    assert twin.instance.asserts == ["env_s.g_assert.p_env"]
    assert job.assumes == []


def test_quasi_static_match_and_verify(tmp_path):
    from open_formal_cdc.config import Assumption
    from open_formal_cdc.jobs import is_environment
    nl = Netlist(NETLIST, "top")
    a = Assumption("q", "quasi_static", {"signals_match": "u.*", "exclude": ["u.en"], "allow": "go",
                                         "allow_value": 0, "verify": False})
    assert is_environment(a, nl)
    raw = parse_config({"design": {"top": "top", "files": ["t.sv"]},
                        "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b"}],
                        "checks": [{"name": "g", "template": "gray", "signal": "q", "clock": "b"}]},
                       tmp_path / "c.yaml")
    build_job(raw, raw.design, nl, raw.checks[0], ["t.sv"], tmp_path / "j", "../rtl", [a])
    w = (tmp_path / "j" / "wrapper_ticks.v").read_text()
    assert "ofcdc_env_quasi_static #(.W(4), .ASSERT(0), .ALLOW_VAL(0)) env_q" in w
    assert ".allow(ofcdc_in_go), .v(ofcdc_s0)" in w


def test_nohazard_job_keeps_cone_script_with_assumption(tmp_path):
    from open_formal_cdc.config import Assumption
    module = NETLIST["modules"]["top"]
    data = {"modules": {"top": {"ports": module["ports"],
                                "netnames": {**module["netnames"], "u_and.d": {"bits": [14]}}}}}
    raw = parse_config({"design": {"top": "top", "files": ["t.sv"]},
                        "clocks": [{"name": "a", "port": "clk_a"}, {"name": "b", "port": "clk_b"}],
                        "inputs": [{"port": "go", "clock": "a"}],
                        "checks": [{"name": "h", "template": "nohazard", "d": "u_and.d",
                                    "inputs": ["u.ptr"], "clock": "b"}]}, tmp_path / "c.yaml")
    env = Assumption("e", "constant", {"signal": "go", "value": 1})
    job = build_job(raw, raw.design, Netlist(data, "top"), raw.checks[0], ["t.sv"],
                    tmp_path / "j", "../rtl", [env])
    sby = (tmp_path / "j" / "job.sby").read_text()
    assert "copy top ofcdc_hazard_dut_h" in sby
    assert "submod -name ofcdc_cone_h @ofcdc_cone_h" in sby
    assert sby.index("memory_collect") < sby.index("submod -name")
    assert "rename -output u_and.d ofcdc_s0" in sby
    assert "connect -port ofcdc_cone_h ofcdc_s1 hz_h_in0" in sby
    assert "select -assert-none %" in sby
    w = (tmp_path / "j" / "wrapper_ticks.v").read_text()
    assert "ofcdc_hazard_dut_h u_ofcdc_hazard_dut_h" in w
    assert ".ofcdc_s0(hz_h_f)" in w and ".hz_h_in0(hz_h_in0)" in w
    assert "c_skew: cover (f != d);" in (tmp_path / "j" / "ofcdc_nohazard.v").read_text()
    assert job.instance.covers == ["chk_h.c_change", "chk_h.c_skew"]
