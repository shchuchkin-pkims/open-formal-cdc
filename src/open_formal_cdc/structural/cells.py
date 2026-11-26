# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Library of synchronizer cells (vendor macros and common primitives).

A cell instance that stays in the netlist (black box, or a module kept with
keep_hierarchy) is treated as a vetted synchronizer: its outputs belong to the
domain of the clock port named for them, and the data inputs listed in 'through'
cross into the cell (scheme of the cell). Other inputs must already be in the
domain of their clock role, otherwise the feed itself is an unsynchronized crossing.

Port roles: 'src' / 'dst' name a clock role in 'clocks'; None marks an asynchronous
input that the cell synchronizes (for example a reset or a level input).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CellSpec:
    module: str
    scheme: str                              # ndff, ndff_bus, gray_bus, handshake, pulse_toggle, reset_sync
    clocks: dict[str, str]                   # role -> clock port
    inputs: dict[str, str | None]            # input port -> role (None: asynchronous)
    outputs: dict[str, str]                  # output port -> role
    through: list[str] = field(default_factory=list)   # inputs whose data crosses to 'dst'


def _x(module, scheme, clocks, inputs, outputs, through):
    return CellSpec(module, scheme, clocks, inputs, outputs, through)


KNOWN_CELLS: dict[str, CellSpec] = {s.module: s for s in [
    # Xilinx XPM CDC macros (UG974)
    _x("xpm_cdc_single", "ndff", {"src": "src_clk", "dst": "dest_clk"},
       {"src_in": "src"}, {"dest_out": "dst"}, ["src_in"]),
    _x("xpm_cdc_array_single", "ndff_bus", {"src": "src_clk", "dst": "dest_clk"},
       {"src_in": "src"}, {"dest_out": "dst"}, ["src_in"]),
    _x("xpm_cdc_gray", "gray_bus", {"src": "src_clk", "dst": "dest_clk"},
       {"src_in_bin": "src", "src_inc_bin": "src"}, {"dest_out_bin": "dst"}, ["src_in_bin", "src_inc_bin"]),
    _x("xpm_cdc_handshake", "handshake", {"src": "src_clk", "dst": "dest_clk"},
       {"src_in": "src", "src_send": "src", "dest_ack": "dst"},
       {"dest_out": "dst", "dest_req": "dst", "src_rcv": "src"}, ["src_in", "src_send", "dest_ack"]),
    _x("xpm_cdc_pulse", "pulse_toggle", {"src": "src_clk", "dst": "dest_clk"},
       {"src_pulse": "src", "src_rst": "src", "dest_rst": "dst"}, {"dest_pulse": "dst"}, ["src_pulse"]),
    _x("xpm_cdc_async_rst", "reset_sync", {"dst": "dest_clk"},
       {"src_arst": None}, {"dest_arst": "dst"}, ["src_arst"]),
    _x("xpm_cdc_sync_rst", "reset_sync", {"dst": "dest_clk"},
       {"src_rst": None}, {"dest_rst": "dst"}, ["src_rst"]),
    # Intel / Altera
    _x("altera_std_synchronizer", "ndff", {"dst": "clk"}, {"din": None}, {"dout": "dst"}, ["din"]),
    _x("altera_std_synchronizer_bundle", "ndff_bus", {"dst": "clk"}, {"din": None}, {"dout": "dst"}, ["din"]),
    # OpenTitan (when kept as a cell)
    _x("prim_flop_2sync", "ndff", {"dst": "clk_i"}, {"d_i": None}, {"q_o": "dst"}, ["d_i"]),
]}


def cell_spec_from_config(d: dict) -> CellSpec:
    """Cell description from the 'cells' section of the configuration."""
    return CellSpec(module=str(d["module"]), scheme=str(d.get("scheme", "user_cell")),
                    clocks=dict(d["clocks"]), inputs=dict(d.get("inputs") or {}),
                    outputs=dict(d.get("outputs") or {}), through=list(d.get("through") or []))
