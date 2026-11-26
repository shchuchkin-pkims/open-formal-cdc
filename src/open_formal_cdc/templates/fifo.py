# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-FIFO: asynchronous FIFO protocol check (flags and data integrity) on its interface."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("fifo")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: wr_clock, wr_en, wr_full (optional), wr_data, rd_clock, rd_en,
    rd_empty (optional), rd_data, depth, read_latency (only 0 for now)."""
    if int(params.get("read_latency", 0)) != 0:
        raise TemplateError(f"check '{check}': only read_latency 0 is supported")
    wclk, rclk = str(need(params, "wr_clock", check)), str(need(params, "rd_clock", check))
    wen, _ = ctx.signal(str(need(params, "wr_en", check)))
    ren, _ = ctx.signal(str(need(params, "rd_en", check)))
    wfull = ctx.signal(str(params["wr_full"]))[0] if params.get("wr_full") else "1'b0"
    rempty = ctx.signal(str(params["rd_empty"]))[0] if params.get("rd_empty") else "1'b0"
    wdat, dw = ctx.signal(str(need(params, "wr_data", check)))
    rdat, rw = ctx.signal(str(need(params, "rd_data", check)))
    if dw != rw:
        raise TemplateError(f"check '{check}': wr_data is {dw} bits, rd_data {rw}")
    depth = int(need(params, "depth", check))
    inst = f"chk_{check}"
    verilog = (f"  ofcdc_fifo #(.DW({dw}), .DEPTH({depth}), .TICKS({ctx.model_param()})) {inst} (\n"
               f"    .act_w({ctx.act(wclk)}), .act_r({ctx.act(rclk)}),\n"
               f"    .edge_w({ctx.edge(wclk)}), .edge_r({ctx.edge(rclk)}),\n"
               f"    .wr_en({wen}), .wr_full({wfull}), .wr_data({wdat}),\n"
               f"    .rd_en({ren}), .rd_empty({rempty}), .rd_data({rdat}));")
    return Instance(["ofcdc_fifo.v"], verilog,
                    [f"{inst}.p_no_overflow", f"{inst}.p_no_underflow", f"{inst}.p_data"],
                    [f"{inst}.c_full", f"{inst}.c_tracked"])
