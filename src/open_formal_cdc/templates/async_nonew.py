# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""M7: no invented values after independent old/new asynchronous input skew."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("async_nonew")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: src - asynchronous source; dst - destination register; clock - receiver clock."""
    src, sw = ctx.signal(str(need(params, "src", check)))
    dst, dw = ctx.signal(str(need(params, "dst", check)))
    if sw != dw:
        raise TemplateError(f"check '{check}': src is {sw} bits, dst {dw}")
    clock = str(need(params, "clock", check))
    if not params.get("skew"):
        raise TemplateError(f"check '{check}': 'skew' must list receiving stages")
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_nonew #(.W({sw})) {inst} (.act({ctx.act(clock)}), "
               f".src({src}), .dst({dst}));")
    return Instance(["ofcdc_nonew.v"], verilog, [f"{inst}.p_nonew"], [f"{inst}.c_new"])
