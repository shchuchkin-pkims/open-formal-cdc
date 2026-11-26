# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-CLKMUX: every output-clock phase lasts at least min_steps global steps."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("clock_mux")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: signal - muxed clock net; min_steps - minimum phase length, at least 2;
    clocks - optional input clock domains that get the same phase-duration assumption."""
    signal, width = ctx.signal(str(need(params, "signal", check)))
    if width != 1:
        raise TemplateError(f"check '{check}': muxed clock must be a single bit")
    min_steps = int(params.get("min_steps", 2))
    if min_steps < 2:
        raise TemplateError(f"check '{check}': min_steps must be at least 2")
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_clock_mux #(.MIN_STEPS({min_steps})) {inst} "
               f"(.act({ctx.init_done()}), .v({signal}));")
    legs = []
    for i, clock in enumerate(params.get("clocks") or []):
        legs.append(f"  ofcdc_clock_leg #(.MIN_STEPS({min_steps})) leg_{i} "
                    f"(.act({ctx.init_done()}), .v({ctx.clock(str(clock))}));")
    if legs:
        verilog += "\n" + "\n".join(legs)
    return Instance(["ofcdc_clock_mux.v", "ofcdc_clock_leg.v"], verilog,
                    [f"{inst}.p_phase"], [f"{inst}.c_change"])
