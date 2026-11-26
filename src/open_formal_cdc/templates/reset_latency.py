# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Reset deassertion latency with optional M6 reset-release injection."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("reset_latency")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: src_reset, tail_reset, clock, max_cycles, reset_active, msi_reset."""
    src, sw = ctx.signal(str(need(params, "src_reset", check)))
    tail, tw = ctx.signal(str(need(params, "tail_reset", check)))
    if sw != 1 or tw != 1:
        raise TemplateError(f"check '{check}': reset inputs must be single bits")
    clock = str(need(params, "clock", check))
    cycles = int(need(params, "max_cycles", check))
    if cycles < 1:
        raise TemplateError(f"check '{check}': max_cycles must be positive")
    active_low = 0 if params.get("reset_active", "low") == "high" else 1
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_reset_latency #(.MAX_CYCLES({cycles}), .ACTIVE_LOW({active_low})) {inst} "
               f"(.clk({ctx.clock(clock)}), .act({ctx.init_done()}), .src_rst({src}), .tail_rst({tail}));")
    return Instance(["ofcdc_reset_latency.v"], verilog, [f"{inst}.p_latency"], [f"{inst}.c_release"])
