# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-GLITCH function-hazard form (model M4) in front of a synchronizer.

A duplicate of the design holds a combinational cone extracted with submod. Yosys
wires the extracted instance itself, including aliases and fanout ports. Only the
cone inputs are overridden with old/new skew models; the original design supplies
the real D and the reference source values.
"""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


@register("nohazard")
def build(check: str, params: dict[str, Any], ctx: Context) -> Instance:
    """Parameters: d - D net of the first synchronizer stage; inputs - all source nets of
    its combinational cone (flops and top-level inputs); clock - destination clock."""
    d, dw = ctx.signal(str(need(params, "d", check)))
    nets = [str(n) for n in need(params, "inputs", check)]
    if not nets:
        raise TemplateError(f"check '{check}': no inputs")
    clk = str(need(params, "clock", check))
    k = f"hz_{check}"
    cone = f"ofcdc_cone_{check}"
    duplicate = f"ofcdc_hazard_dut_{check}"
    dport = ctx.dut_name(str(params["d"]))
    script = [f"cd ..", f"copy {ctx.top_name()} {duplicate}", f"cd {duplicate}",
              f"select -set {cone} w:{dport} %cie* c:* %i",
              f"submod -name {cone} @{cone}"]
    lines = [f"  wire [{dw - 1}:0] {k}_f;"]
    cap = f"{ctx.edge(clk)} & {ctx.act(clk)} & {ctx.init_done()}"
    connections = {dport: f"{k}_f"}
    top_skew = set()
    for i, n in enumerate(ctx.data_inputs()):
        sig, w = ctx.signal(n)
        port = ctx.dut_name(n)
        wire = f"{k}_pin{i}"
        lines.append(f"  wire [{w - 1}:0] {wire};")
        lines.append(f"  ofcdc_skew_cap #(.W({w})) {k}_pmsi{i} "
                     f"(.cap({cap}), .d({sig}), .d_seen({wire}), .alt());")
        connections[port] = wire
        top_skew.add(port)
    skew_inputs: list[tuple[str, int]] = []
    seen = set()
    for i, n in enumerate(nets):
        base = n.split("[")[0] if n not in ctx.known_nets() else n
        sig, w = ctx.signal(base)
        port = ctx.dut_name(base)
        if port in seen or port in top_skew:
            continue
        seen.add(port)
        wire = f"{k}_in{i}"
        lines.append(f"  ofcdc_skew_cap #(.W({w})) {k}_msi{i} "
                     f"(.cap({cap}), .d({sig}), .d_seen({wire}), .alt());")
        skew_inputs.append((wire, w))
        script += [f"add -input {wire} {w}", f"connect -port {cone} {port} {wire}"]
    script += [f"cd {cone}", "select i:*"]
    script += [f"select -del i:{port}" for port in seen]
    script += [f"select -del i:{ctx.dut_name(n)}" for n in ctx.input_ports()]
    script += ["select -assert-none %", "cd .."]
    lines.append(f"  ofcdc_nohazard #(.W({dw})) chk_{check} "
                 f"(.cap({cap}), .d({d}), .f({k}_f));")
    ctx.add_design(duplicate, connections, skew_inputs)
    return Instance(["ofcdc_skew_cap.v", "ofcdc_nohazard.v"], "\n".join(lines),
                    [f"chk_{check}.p_nohazard"],
                    [f"chk_{check}.c_change", f"chk_{check}.c_skew"], script=script)
