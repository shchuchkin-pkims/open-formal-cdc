# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""RDC-001: reset deassertion only at a destination clock edge."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("reset_release")
@register("srst_release")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: signal - reset net; clock - destination clock; reset_active - high/low."""
    signal, width = ctx.signal(str(need(params, "signal", check)))
    if width != 1:
        raise TemplateError(f"check '{check}': reset signal must be a single bit")
    clock = str(need(params, "clock", check))
    active_low = 0 if params.get("reset_active", "low") == "high" else 1
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_reset_release #(.ACTIVE_LOW({active_low})) {inst} "
               f"(.act({ctx.init_done()}), .cap({ctx.edge(clock)}), .rst({signal}));")
    return Instance(["ofcdc_reset_release.v"], verilog, [f"{inst}.p_release"], [f"{inst}.c_release"])
