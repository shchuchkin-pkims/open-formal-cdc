# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Bounded capture of stable D data into a destination register."""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("settled")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: data, dst (nets or equally sized lists), clock and stable_edges."""
    data_param = need(params, "data", check)
    dst_param = need(params, "dst", check)
    grouped = isinstance(data_param, list) or isinstance(dst_param, list)
    datas = data_param if isinstance(data_param, list) else [data_param]
    dsts = dst_param if isinstance(dst_param, list) else [dst_param]
    if not datas or len(datas) != len(dsts):
        raise TemplateError(f"check '{check}': data and dst lists must have equal nonzero length")
    clock = str(need(params, "clock", check))
    edges = int(need(params, "stable_edges", check))
    if edges < 1:
        raise TemplateError(f"check '{check}': stable_edges must be positive")
    verilog: list[str] = []
    asserts: list[str] = []
    covers: list[str] = []
    for i, (data_net, dst_net) in enumerate(zip(datas, dsts)):
        data, dw = ctx.signal(str(data_net))
        dst, qw = ctx.signal(str(dst_net))
        if dw != qw:
            raise TemplateError(f"check '{check}': data is {dw} bits, dst {qw}")
        inst = f"chk_{check}_{i}" if grouped else f"chk_{check}"
        verilog.append(f"  ofcdc_settled #(.W({dw}), .STABLE_EDGES({edges})) {inst} "
                       f"(.cap({ctx.edge(clock)}), .act({ctx.act(clock)}), .data({data}), .dst({dst}));")
        asserts.append(f"{inst}.p_settled")
        covers.append(f"{inst}.c_settled")
    return Instance(["ofcdc_settled.v"], "\n".join(verilog), asserts, covers)
