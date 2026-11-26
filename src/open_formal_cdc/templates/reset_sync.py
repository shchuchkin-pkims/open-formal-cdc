# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-RST: asynchronous assertion and synchronous staged deassertion of a reset synchronizer."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("reset_sync")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: signal - vector of synchronizer stages; reset - asynchronous reset port;
    clock - destination clock."""
    sig, width = ctx.signal(str(need(params, "signal", check)))
    if width < 2:
        raise TemplateError(f"check '{check}': reset synchronizer needs at least two stages")
    reset, rw = ctx.signal(str(need(params, "reset", check)))
    if rw != 1:
        raise TemplateError(f"check '{check}': reset must be a single bit")
    clk = str(need(params, "clock", check))
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_reset_sync #(.N({width})) {inst} "
               f"(.clk({ctx.clock(clk)}), .rst_n({reset}), .v({sig}));")
    return Instance(["ofcdc_reset_sync.v"], verilog, [f"{inst}.p_stages"], [f"{inst}.c_release"])
