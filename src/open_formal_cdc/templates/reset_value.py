# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""RDC-002: the destination holds its reset value while the source reset is asserted."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("reset_value")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: reset - source reset; reset_active - high/low; dst - consumer output;
    value - consumer reset value."""
    reset, rw = ctx.signal(str(need(params, "reset", check)))
    dst, dw = ctx.signal(str(need(params, "dst", check)))
    if rw != 1 or dw != 1:
        raise TemplateError(f"check '{check}': reset and dst must be single bits")
    active_low = 0 if params.get("reset_active", "low") == "high" else 1
    value = int(need(params, "value", check))
    if value not in (0, 1):
        raise TemplateError(f"check '{check}': value must be 0 or 1")
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_reset_value #(.VALUE({value}), .ACTIVE_LOW({active_low})) {inst} "
               f"(.act({ctx.init_done()}), .reset({reset}), .dst({dst}));")
    return Instance(["ofcdc_reset_value.v"], verilog, [f"{inst}.p_value"], [f"{inst}.c_reset"])
