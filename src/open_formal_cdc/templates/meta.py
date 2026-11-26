# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-META: the destination never shows a value the source has never held
(checked with the metastability model on the first synchronizer stage)."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("nonew")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: src and dst - nets or lists of nets (same total width);
    clocks - active domains; msi/m5 - metastability models (see jobs.py)."""
    def vector(value: Any) -> tuple[str, int]:
        if not isinstance(value, list):
            return ctx.signal(str(value))
        if not value:
            raise TemplateError(f"check '{check}': src/dst lists must not be empty")
        signals = [ctx.signal(str(net)) for net in value]
        return "{" + ", ".join(sig for sig, _ in signals) + "}", sum(w for _, w in signals)

    src, sw = vector(need(params, "src", check))
    dst, dw = vector(need(params, "dst", check))
    if sw != dw:
        raise TemplateError(f"check '{check}': src is {sw} bits, dst {dw}")
    act = " & ".join([ctx.init_done()] + [ctx.act(c) for c in params.get("clocks") or []])
    inst = f"chk_{check}"
    verilog = f"  ofcdc_nonew #(.W({sw})) {inst} (.act({act}), .src({src}), .dst({dst}));"
    return Instance(["ofcdc_nonew.v"], verilog, [f"{inst}.p_nonew"], [f"{inst}.c_new"])
