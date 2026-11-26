# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-PULSE: a source value is held for at least N destination edges (no lost pulses)."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, need, register


@register("pulse")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: signal - source of the synchronizer; clock - destination clock;
    src_clock - source clock (reset gating); min_edges - N (default 2)."""
    sig, width = ctx.signal(str(need(params, "signal", check)))
    dst = str(need(params, "clock", check))
    src = str(params.get("src_clock", dst))
    n = int(params.get("min_edges", 2))
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_pulse #(.W({width}), .N({n}), .TICKS({ctx.model_param()})) {inst} ("
               f".act({ctx.act(src)} & {ctx.act(dst)}), .edge_d({ctx.edge(dst)}), .src({sig}));")
    return Instance(["ofcdc_pulse.v"], verilog, [f"{inst}.p_pulse"], [f"{inst}.c_change"])
