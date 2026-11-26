# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-ENV: environment assumptions, used as 'assume' in checks and as 'assert' in twins.

Parameters: signal (one net), signals (list of nets, concatenated) or signals_match
(glob over net names, with exclude); verify: false - a promise about the environment,
not checked by a twin; value (constant);
clock (hamming1); allow and allow_value (quasi_static: changes only while allow ==
allow_value); protocol, antecedent and consequent (clocked protocol); steps (internal
trace_block); mode - assume (default) or assert.
"""

from __future__ import annotations

from typing import Any

from . import Context, Instance, TemplateError, need, register


def _signals(check: str, params: dict[str, Any], ctx: Context) -> tuple[str, int]:
    nets = params.get("signals")
    if params.get("signals_match"):
        nets = ctx.match(str(params["signals_match"]), [str(e) for e in params.get("exclude") or []])
        if not nets:
            raise TemplateError(f"assumption '{check}': no net matches '{params['signals_match']}'")
    if nets is None:
        nets = [need(params, "signal", check)]
    if not nets:
        raise TemplateError(f"assumption '{check}': empty signal list")
    sigs = [ctx.signal(str(n)) for n in nets]
    if len(sigs) == 1:
        return sigs[0]
    return "{" + ", ".join(s for s, _ in sigs) + "}", sum(w for _, w in sigs)


def _trace_block(check: str, params: dict[str, Any], ctx: Context, mode: str) -> Instance:
    steps = params.get("steps") or []
    if not steps:
        raise TemplateError(f"assumption '{check}': empty trace block")
    act = ctx.init_done()
    literals = {}

    def literal(name: str, value: int) -> str:
        key = (name, int(value))
        if key not in literals:
            sig, width = ctx.signal(name)
            if width != 1:
                raise TemplateError(f"assumption '{check}': trace literals must be single bits")
            literals[key] = sig if int(value) else f"!{sig}"
        return literals[key]

    expressions = [" && ".join(literal(str(name), int(value)) for name, value in sorted(step.items()))
                   for step in steps]
    if any(not expression for expression in expressions):
        raise TemplateError(f"assumption '{check}': empty step in trace block")
    n = len(expressions)
    lines = [f"  wire block_{check}_{i} = {expression};" for i, expression in enumerate(expressions)]
    lines += [f"  reg [{n - 1}:0] block_{check}_matched = 0;",
              f"  reg block_{check}_started = 1'b0;",
              f"  always @($global_clock) if (!{act}) begin",
              f"    block_{check}_matched <= 0; block_{check}_started <= 1'b0; end else begin",
              f"    block_{check}_started <= 1'b1;",
              f"    block_{check}_matched[0] <= !block_{check}_started && block_{check}_0;"]
    lines += [f"    block_{check}_matched[{i}] <= block_{check}_matched[{i - 1}] && block_{check}_{i};"
              for i in range(1, n)]
    lines.append("  end")
    forbidden = (f"block_{check}_matched[0] && block_{check}_0" if n == 1 else
                 f"block_{check}_matched[{n - 2}] && block_{check}_{n - 1}")
    keyword = "assert" if mode == "assert" else "assume"
    lines.append(f"  always @(*) if ({act}) p_env: {keyword} (!({forbidden}));")
    return Instance([], "\n".join(lines), ["p_env"] if mode == "assert" else [], [])


def _protocol(check: str, params: dict[str, Any], ctx: Context, mode: str) -> Instance:
    kinds = {"always": 0, "implies": 1, "next": 2, "and": 3, "and_next": 4, "mixed_next": 5}
    kind = str(need(params, "protocol", check))
    if kind not in kinds:
        raise TemplateError(f"assumption '{check}': unknown protocol template '{kind}'")

    def literal(data) -> str:
        sig, width = ctx.signal(str(data["signal"]))
        if width != 1:
            raise TemplateError(f"assumption '{check}': protocol literals must be single bits")
        return sig if data.get("positive", True) else f"!{sig}"

    antecedent = [literal(a) for a in params.get("antecedent") or []]
    a1 = antecedent[0] if antecedent else "1'b0"
    a2 = antecedent[1] if len(antecedent) > 1 else "1'b0"
    a3 = literal(need(params, "consequent", check))
    clock = str(need(params, "clock", check))
    inst = f"env_{check}"
    verilog = (f"  ofcdc_env_protocol #(.T({kinds[kind]}), .ASSERT({1 if mode == 'assert' else 0})) "
               f"{inst} (.clk({ctx.clock(clock)}), .act({ctx.act(clock)}), "
               f".a1({a1}), .a2({a2}), .a3({a3}));")
    if mode == "assert":
        return Instance(["ofcdc_env_protocol.v"], verilog, [f"{inst}.g_assert.p_env"],
                        [f"{inst}.g_assert.c_env_act"])
    return Instance(["ofcdc_env_protocol.v"], verilog, [], [])


def _env(kind: str, check: str, params: dict[str, Any], ctx: Context) -> Instance:
    mode = str(params.get("mode", "assume"))
    if mode not in ("assume", "assert"):
        raise TemplateError(f"assumption '{check}': mode must be assume or assert")
    if kind == "protocol":
        return _protocol(check, params, ctx, mode)
    if kind == "trace_block":
        return _trace_block(check, params, ctx, mode)
    inst = f"env_{check}"
    if kind == "clock_select":
        sel_d, dw = ctx.signal(str(need(params, "select_d", check)))
        sel, sw = ctx.signal(str(need(params, "select", check)))
        on, ow = ctx.signal(str(need(params, "on", check)))
        if dw != 1 or sw != 1:
            raise TemplateError(f"assumption '{check}': select_d and select must be single bits")
        prm = [f".W({ow})", f".ON0({int(params.get('on0', 1))})",
               f".ON1({int(params.get('on1', 2))})", f".ASSERT({1 if mode == 'assert' else 0})",
               f".INIT({int(params.get('init', 0))})"]
        ports = [f".act({ctx.init_done()})", f".sel_d({sel_d})", f".sel({sel})", f".on({on})"]
    else:
        sig, width = _signals(check, params, ctx)
        prm = [f".W({width})", f".ASSERT({1 if mode == 'assert' else 0})"]
        ports = [f".act({ctx.init_done()})", f".v({sig})"]
    if kind == "constant":
        prm.append(f".VALUE({width}'d{int(need(params, 'value', check))})")
    if kind == "quasi_static":
        allow, aw = ctx.signal(str(need(params, "allow", check)))
        if aw != 1:
            raise TemplateError(f"assumption '{check}': 'allow' must be a single bit")
        prm.append(f".ALLOW_VAL({int(params.get('allow_value', 0))})")
        ports = [f".act({ctx.init_done()})", f".allow({allow})", f".v({sig})"]
    if kind == "hamming1":
        clk = str(need(params, "clock", check))
        ports = [f".clk({ctx.clock(clk)})", f".act({ctx.act(clk)})", f".v({sig})"]
    verilog = f"  ofcdc_env_{kind} #({', '.join(prm)}) {inst} ({', '.join(ports)});"
    if mode == "assert":
        return Instance(["ofcdc_env.v"], verilog, [f"{inst}.g_assert.p_env"],
                        [f"{inst}.g_assert.c_env_act"])
    return Instance(["ofcdc_env.v"], verilog, [], [])


for _kind in ("constant", "static", "onehot0", "hamming1", "quasi_static", "clock_select", "protocol",
              "trace_block"):
    register(f"env_{_kind}")(lambda c, p, x, _k=_kind: _env(_k, c, p, x))
