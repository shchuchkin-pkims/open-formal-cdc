# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""T-ENV: environment assumptions, used as 'assume' in checks and as 'assert' in twins.

Parameters: signal (one net), signals (list of nets, concatenated) or signals_match
(glob over net names, with exclude); verify: false - a promise about the environment,
not checked by a twin; value (constant);
clock (hamming1); allow and allow_value (quasi_static: changes only while allow ==
allow_value); mode - assume (default) or assert.
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


def _env(kind: str, check: str, params: dict[str, Any], ctx: Context) -> Instance:
    mode = str(params.get("mode", "assume"))
    if mode not in ("assume", "assert"):
        raise TemplateError(f"assumption '{check}': mode must be assume or assert")
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


for _kind in ("constant", "static", "onehot0", "hamming1", "quasi_static", "clock_select"):
    register(f"env_{_kind}")(lambda c, p, x, _k=_kind: _env(_k, c, p, x))
