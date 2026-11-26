# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from open_formal_cdc.focus import en_stable_cuts, gray_cuts, propose_cuts
from open_formal_cdc.structural import Graph


def graph():
    cells = {
        "$driver$data_q": {
            "type": "$dff", "parameters": {},
            "connections": {"CLK": [2], "D": [4], "Q": [6]},
            "port_directions": {"CLK": "input", "D": "input", "Q": "output"},
        },
        "$driver$dst_data_q": {
            "type": "$dff", "parameters": {},
            "connections": {"CLK": [3], "D": [6], "Q": [7]},
            "port_directions": {"CLK": "input", "D": "input", "Q": "output"},
        },
        "$and$cap": {
            "type": "$and", "parameters": {},
            "connections": {"A": [6], "B": [7], "Y": [8]},
            "port_directions": {"A": "input", "B": "input", "Y": "output"},
        },
    }
    data = {"modules": {"top": {
        "ports": {"clk_a": {"direction": "input", "bits": [2]},
                  "clk_b": {"direction": "input", "bits": [3]},
                  "data_in": {"direction": "input", "bits": [4]}},
        "cells": cells,
        "netnames": {"data_q": {"bits": [6]}, "dst_data_q": {"bits": [7]}, "cap": {"bits": [8]}},
    }}}
    return Graph.from_json(data, "top")


def test_enable_boundary_is_proposed():
    assert en_stable_cuts(graph(), {"data": "data_q", "enable": "cap"}) == ["dst_data_q"]


def test_direct_enable_has_no_boundary():
    assert en_stable_cuts(graph(), {"data": "data_q", "enable": "dst_data_q"}) == []


def test_gray_next_state_boundary():
    params = {"signal": "dst_data_q"}
    assert gray_cuts(graph(), params) == ["data_q"]
    assert propose_cuts(graph(), "gray", params) == ["data_q"]
