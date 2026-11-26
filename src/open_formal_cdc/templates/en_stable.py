# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-EN: source data is stable while the destination capture enable is active."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("en_stable")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: data - source data; enable - capture enable (1 bit, destination
    domain); clock - destination clock; enable_active - high (default) or low."""
    data, width = ctx.signal(str(need(params, "data", check)))
    en, ew = ctx.signal(str(need(params, "enable", check)))
    if ew != 1:
        raise TemplateError(f"check '{check}': enable must be 1 bit wide, not {ew}")
    if str(params.get("enable_active", "high")) == "low":
        en = f"~{en}"
    clk = str(need(params, "clock", check))
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_en_stable #(.W({width})) {inst} (.clk({ctx.clock(clk)}), "
               f".act({ctx.act(clk)}), .en({en}), .data({data}));")
    return Instance(["ofcdc_en_stable.v"], verilog, [f"{inst}.p_stable"],
                    [f"{inst}.c_capture", f"{inst}.c_data_change"])
