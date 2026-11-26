# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Bounded propagation latency of a monotonic rising control signal."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("rise_latency")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: src, dst, clock and max_cycles; src must be monotonic 0 -> 1."""
    src, sw = ctx.signal(str(need(params, "src", check)))
    dst, dw = ctx.signal(str(need(params, "dst", check)))
    if sw != 1 or dw != 1:
        raise TemplateError(f"check '{check}': src and dst must be single bits")
    clock = str(need(params, "clock", check))
    cycles = int(need(params, "max_cycles", check))
    if cycles < 1:
        raise TemplateError(f"check '{check}': max_cycles must be positive")
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_rise_latency #(.MAX_CYCLES({cycles})) {inst} "
               f"(.clk({ctx.clock(clock)}), .act({ctx.act(clock)}), .src({src}), .dst({dst}));")
    return Instance(["ofcdc_rise_latency.v"], verilog,
                    [f"{inst}.p_latency"], [f"{inst}.c_wait", f"{inst}.c_risen"])
