# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-HS: the handshake request changes only after the acknowledge caught up."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("hs_req")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: req - request register; ack - acknowledge synchronized into the
    source domain; clock - source clock."""
    req, rw = ctx.signal(str(need(params, "req", check)))
    ack, aw = ctx.signal(str(need(params, "ack", check)))
    if rw != 1 or aw != 1:
        raise TemplateError(f"check '{check}': req and ack must be single bits")
    clk = str(need(params, "clock", check))
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_hs_req {inst} (.clk({ctx.clock(clk)}), .act({ctx.act(clk)}), "
               f".req({req}), .ack_s({ack}));")
    return Instance(["ofcdc_hs_req.v"], verilog, [f"{inst}.p_req"], [f"{inst}.c_req"])
