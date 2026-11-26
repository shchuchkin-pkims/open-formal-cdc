# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-RST capture: no destination capture during source reset or its release window."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("rdc_capture")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: src_reset - source reset; reset_active - high or low (default);
    dst_reset - optional destination reset with dst_reset_active; dst_valid - optional capture
    enable (constant 1 if absent); valid_active - high (default) or low; dst_clock - destination
    clock; release_cycles - blocked destination edges after release."""
    if params.get("dst_valid"):
        valid, width = ctx.signal(str(params["dst_valid"]))
        if width != 1:
            raise TemplateError(f"check '{check}': dst_valid must be a single bit")
    else:
        valid, width = "1'b1", 1
    if params.get("valid_active", "high") == "low":
        valid = f"~{valid}"
    reset, rw = ctx.signal(str(need(params, "src_reset", check)))
    if rw != 1:
        raise TemplateError(f"check '{check}': src_reset must be a single bit")
    if params.get("reset_active", "low") == "high":
        reset = f"~{reset}"
    clk = str(need(params, "dst_clock", check))
    cycles = int(params.get("release_cycles", 1))
    if cycles < 1:
        raise TemplateError(f"check '{check}': release_cycles must be positive")
    inst = f"chk_{check}"
    if params.get("dst_reset"):
        dst_reset, dw = ctx.signal(str(params["dst_reset"]))
        if dw != 1:
            raise TemplateError(f"check '{check}': dst_reset must be a single bit")
        if params.get("dst_reset_active", "low") == "high":
            dst_reset = f"~{dst_reset}"
        act = f"{ctx.init_done()} & {dst_reset}"
    elif params.get("dst_reset_active") == "none":
        act = ctx.init_done()
    else:
        act = f"{ctx.act(clk)} & {ctx.init_done()}"
    cap = f"{ctx.edge(clk)} & {ctx.init_done()}"
    verilog = (f"  ofcdc_rdc_capture #(.RELEASE_CYCLES({cycles})) {inst} "
               f"(.act({act}), .cap({cap}), .src_rst_n({reset}), .dst_valid({valid}));")
    return Instance(["ofcdc_rdc_capture.v"], verilog, [f"{inst}.p_capture"], [f"{inst}.c_capture"])
