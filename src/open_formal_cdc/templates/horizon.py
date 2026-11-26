# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Reach a specified global-step horizon, used for assumption satisfiability."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, need, register


@register("horizon")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    depth = int(need(params, "depth", check))
    if depth < 1:
        raise ValueError("horizon depth must be positive")
    verilog = f"""  reg [31:0] horizon_{check} = 0;
  always @($global_clock) horizon_{check} <= horizon_{check} + 1'b1;
  always @(*) c_horizon: cover (horizon_{check} == {depth - 1});"""
    return Instance([], verilog, [], ["c_horizon"])
