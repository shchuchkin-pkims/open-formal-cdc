# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-GRAY: Gray code on the source registers."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, need, register


@register("gray")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: signal - source bus; clock - source clock."""
    sig, width = ctx.signal(str(need(params, "signal", check)))
    clk = str(need(params, "clock", check))
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_gray #(.W({width})) {inst} (.clk({ctx.clock(clk)}), "
               f".act({ctx.act(clk)}), .v({sig}));")
    return Instance(["ofcdc_gray.v"], verilog, [f"{inst}.p_gray"], [f"{inst}.c_change"])
