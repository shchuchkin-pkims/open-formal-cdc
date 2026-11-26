# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-GLITCH and T-CONV: at most one of the given source bits changes per global step."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("onechange")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: signals - list of source nets; clocks - domains that must be out of
    reset for the check (default: none besides the initial reset); role - glitch
    (default) or convergence (advisory: a counterexample asks for review)."""
    nets = list(need(params, "signals", check))
    if not nets:
        raise TemplateError(f"check '{check}': empty signal list")
    sigs = [ctx.signal(str(n)) for n in nets]
    width = sum(w for _, w in sigs)
    cat = sigs[0][0] if len(sigs) == 1 else "{" + ", ".join(s for s, _ in sigs) + "}"
    act = " & ".join([ctx.init_done()] + [ctx.act(c) for c in params.get("clocks") or []])
    inst = f"chk_{check}"
    verilog = f"  ofcdc_onechange #(.W({width})) {inst} (.act({act}), .v({cat}));"
    return Instance(["ofcdc_onechange.v"], verilog, [f"{inst}.p_onechange"], [f"{inst}.c_change"])
