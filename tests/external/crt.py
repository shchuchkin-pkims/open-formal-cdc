# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Regression on adibis/cdc-rdc-tests (Apache-2.0), pinned commit.

The suite gives, per case, the expected rule findings (rule id + source line).
Only a subset of rules maps onto what Open Formal CDC reports today; the other rules
are ignored in the score. Mapping:
  CDC-001  single-bit crossing without a synchronizer            (scheme none, width 1)
  CDC-004  multi-bit crossing without coherence                  (scheme none, width > 1;
           ndff_bus whose source is not proven Gray)
  CDC-003  logic before a synchronizer, flop sources              (ndff with combo logic)
  CDC-006  logic before a synchronizer, port sources              (ndff with combo logic)
  CDC-012  gated bus whose data is not held stable                (mux_enable with a
           counterexample of the data-stability check; needs --formal)
  CDC-024  one source feeding several synchronizers               (divergence)
  CDC-005  synchronizers of one source reconverging                (convergence, one source)
  CDC-017  transparent latch on a crossing path                    (logic 'latch')

Environment assumption of this harness: the suite's SDC does not declare resets, so
input ports named like rst, rst_n, reset, arst_n are taken as resets that are asserted
only during the initial reset (they are neither crossing sources nor free inputs).

Usage:
  python tests/external/crt.py [--executor ssh:user@host:key] [--formal] [--case NAME ...]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from open_formal_cdc.config import Clock, Input, parse_config  # noqa: E402
from open_formal_cdc.executor import make_executor  # noqa: E402
from open_formal_cdc.flow import run as flow_run  # noqa: E402
from open_formal_cdc.sdc import load_sdc  # noqa: E402
from open_formal_cdc.structural import Graph, analyze  # noqa: E402
from open_formal_cdc.structural.graph import (  # noqa: E402
    ASYNC_RESET_PORTS, FF_TYPES, INV_TYPES, PASS_TYPES, SYNC_RESET_PORTS,
)

REPO_URL = "https://github.com/adibis/cdc-rdc-tests"
COMMIT = "737825c08067c9c76730bd648474b300ce0c2d93"
CACHE = ROOT / "tests" / "external" / "cache" / "cdc-rdc-tests"
WORK = ROOT / "build" / "crt"
SUPPORTED = {"CDC-001", "CDC-003", "CDC-004", "CDC-005", "CDC-006", "CDC-012", "CDC-017", "CDC-024"}


def fetch() -> Path:
    if not (CACHE / ".git").exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", REPO_URL, str(CACHE)], check=True)
    subprocess.run(["git", "-C", str(CACHE), "checkout", "-q", COMMIT], check=True)
    return CACHE


def cases(repo: Path, only: list[str] | None) -> list[dict]:
    out = []
    for m in sorted((repo / "cases").glob("*/*/manifest.json")):
        j = json.loads(m.read_text())
        if only and j["id"] not in only:
            continue
        j["dir"] = m.parent
        out.append(j)
    return out


def build_netlists(cs: list[dict], executor_spec: str, jobs: int) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for c in cs:
        d = WORK / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "design.sv").write_bytes((c["dir"] / c["design"]).read_bytes())
        (d / "frontend.ys").write_text(
            f"read_slang design.sv --top {c['top']}\nhierarchy -top {c['top']}\nproc\nflatten\n"
            "opt_clean\nwrite_json netlist.json\n")
    script = (f"cd {shlex.quote(str(WORK))} && ls -d */ | xargs -P {jobs} -I{{}} bash -c "
              "'cd {} && rm -f netlist.json && yosys -q -l yosys.log frontend.ys > /dev/null 2>&1; true'")
    ex = make_executor(executor_spec)
    ex.sync_up(WORK)
    ex.run(script, WORK, timeout=1800)
    ex.sync_down(WORK)


def config_for(c: dict):
    sdc = load_sdc(c["dir"] / c["sdc"]) if c.get("sdc") else None
    clocks = [Clock(k.name, k.port) for k in (sdc.clocks if sdc else []) if k.port]
    names = {k.name for k in clocks}
    inputs = [Input(p, k) for p, k in (sdc.input_clock.items() if sdc else [])]
    for k in (sdc.clocks if sdc else []):
        if not k.port:      # virtual clock: inputs typed to it get its own domain
            names.add(k.name)
    dom = sdc.domain_map() if sdc else {}
    return clocks, inputs, dom, sdc


RESET_NAME = re.compile(r"^(a?rst|a?reset|rst_?async)(_?n|_b)?$", re.IGNORECASE)


def reset_ports(netlist: dict, top: str) -> list[tuple[str, bool]]:
    """Input ports that look like resets or drive a flip-flop reset pin."""
    module = netlist["modules"][top]
    ports = module["ports"]
    out = {}
    for n, p in ports.items():
        if p["direction"] == "input" and RESET_NAME.match(n):
            out[n] = n.lower().endswith(("_n", "_b")) or n.lower().endswith("rstn")
    bit_port = {b: n for n, p in ports.items() if p["direction"] == "input" for b in p["bits"]}
    drivers = {}
    for cell in module.get("cells", {}).values():
        for port, direction in cell.get("port_directions", {}).items():
            if direction == "output":
                for bit in cell.get("connections", {}).get(port, []):
                    drivers[bit] = cell

    def root(bit, active_low, depth=0):
        if bit in bit_port:
            return bit_port[bit], active_low
        cell = drivers.get(bit)
        if cell is None or depth > 64:
            return None
        if cell["type"] in PASS_TYPES | INV_TYPES:
            if cell["type"] in INV_TYPES:
                active_low = not active_low
            bits = cell.get("connections", {}).get("A", [])
            return root(bits[0], active_low, depth + 1) if bits else None
        return None

    for cell in module.get("cells", {}).values():
        if cell["type"] not in FF_TYPES:
            continue
        for port in ASYNC_RESET_PORTS | SYNC_RESET_PORTS:
            bits = cell.get("connections", {}).get(port, [])
            if not bits:
                continue
            polarity = str(cell.get("parameters", {}).get(f"{port}_POLARITY", "1")).lstrip("0")
            found = root(bits[0], not bool(polarity))
            if found:
                name, active_low = found
                out[name] = active_low
    return sorted(out.items())


def findings(st, verdicts: dict[str, str] | None) -> list[tuple[str, int | None, str]]:
    out = []
    port_heads = set()
    latches = set()
    for x in st.crossings:
        width = len({d for _, d in x.bits})
        if x.logic == "latch":
            if x.latch not in latches:                     # once per latch
                latches.add(x.latch)
                out.append(("CDC-017", x.latch_line, x.name))
        elif x.scheme == "none":
            out.append(("CDC-004" if width > 1 else "CDC-001", x.dst_line, x.name))
        elif x.scheme in ("ndff", "ndff_bus") and x.src_kind == "input":
            if x.dst not in port_heads:                    # once per first stage
                port_heads.add(x.dst)
                out.append(("CDC-006", x.dst_line, x.name))
        elif x.scheme in ("ndff", "ndff_bus") and x.logic == "combo":
            out.append(("CDC-003", x.dst_line, x.name))
        elif x.scheme in ("ndff_bus", "gray_bus") and x.logic != "between_stages":
            v = (verdicts or {}).get(x.name)
            if (x.scheme == "ndff_bus" and v != "safe") or (x.scheme == "gray_bus" and v == "unsafe"):
                out.append(("CDC-004", x.dst_line, x.name))
        elif x.scheme == "mux_enable" and verdicts is not None:
            if verdicts.get(x.name) == "unsafe":
                out.append(("CDC-012", x.src_line, x.name))
    for d in st.divergence:
        out.append(("CDC-024", d["src_line"], d["src"]))
    div_sets = [set(d["crossings"]) for d in st.divergence]
    for g in st.convergence:
        if g.get("direct", True) and any(len(set(g["crossings"]) & ds) >= 2 for ds in div_sets):
            line = next((x.src_line for x in st.crossings if x.src == g["sources"][0]), None)
            out.append(("CDC-005", line, g["at"]))
    return out


def formal_verdicts(c: dict, executor_spec: str) -> dict[str, str]:
    clocks, inputs, dom, _ = config_for(c)
    nl = json.loads((WORK / c["id"] / "netlist.json").read_text())
    rsts = reset_ports(nl, c["top"])
    rnames = {r for r, _ in rsts}
    raw = {"design": {"top": c["top"], "files": [str(WORK / c["id"] / "design.sv")]},
           "clocks": [{"name": k.name, "port": k.port} for k in clocks],
           "resets": [{"port": r, "active": "low" if low else "high"} for r, low in rsts],
           "inputs": [{"port": i.port, "clock": i.clock} for i in inputs
                      if i.clock in {k.name for k in clocks} and i.port not in rnames],
           "options": {"time_models": ["ticks"], "timeout": 120}}
    cfg = parse_config(raw, WORK / c["id"] / "ofcdc.yaml")
    res = flow_run(cfg, WORK / c["id"] / "ofcdc", make_executor(executor_spec), log=lambda s: None)
    return {v.crossing: v.verdict for v in res.verdicts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--executor", default=os.environ.get("OFCDC_EXECUTOR", "local"))
    ap.add_argument("--formal", action="store_true", help="run formal checks for ndff_bus/mux_enable")
    ap.add_argument("--case", action="append")
    ap.add_argument("--no-build", action="store_true", help="reuse netlists in build/crt")
    ap.add_argument("-j", type=int, default=16)
    args = ap.parse_args()
    repo = fetch()
    cs = cases(repo, args.case)
    if not args.no_build:
        build_netlists(cs, args.executor, args.j)
    formal: dict[str, dict[str, str]] = {}
    if args.formal:
        from concurrent.futures import ThreadPoolExecutor
        need = []
        for c in cs:
            nl = WORK / c["id"] / "netlist.json"
            if not nl.exists():
                continue
            clocks, inputs, dom, sdc = config_for(c)
            nlj = json.loads(nl.read_text())
            rn = {r for r, _ in reset_ports(nlj, c["top"])}
            st = analyze(Graph.from_json(nlj, c["top"]), clocks, [i for i in inputs if i.port not in rn], rn,
                         dom, dict(sdc.output_clock) if sdc else None)
            if any(x.scheme in ("ndff_bus", "mux_enable", "gray_bus") for x in st.crossings):
                need.append(c)
        print(f"formal checks for {len(need)} case(s)", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for c, v in zip(need, pool.map(lambda c: formal_verdicts(c, args.executor), need)):
                formal[c["id"]] = v
    tp = fp = fn = 0
    rule_stats = collections.defaultdict(lambda: [0, 0, 0])   # tp, fp, fn per rule
    passed = 0
    report = []
    for c in cs:
        nl = WORK / c["id"] / "netlist.json"
        exp = collections.Counter(e["rule"] for e in c["expect"] if e["rule"] in SUPPORTED)
        exp_lines = collections.Counter((e["rule"], e.get("line")) for e in c["expect"] if e["rule"] in SUPPORTED)
        if not nl.exists():
            report.append((c["id"], "NO NETLIST", dict(exp), {}))
            fn += sum(exp.values())
            continue
        clocks, inputs, dom, sdc = config_for(c)
        nlj = json.loads(nl.read_text())
        rnames = {r for r, _ in reset_ports(nlj, c["top"])}
        st = analyze(Graph.from_json(nlj, c["top"]), clocks, [i for i in inputs if i.port not in rnames], rnames, dom,
                     dict(sdc.output_clock) if sdc else None)
        verdicts = formal.get(c["id"]) if args.formal else None
        if args.formal and verdicts is None:
            verdicts = {}
        got_list = findings(st, verdicts)
        got = collections.Counter(r for r, _, _ in got_list)
        got_lines = collections.Counter((r, ln) for r, ln, _ in got_list)
        for r in SUPPORTED:
            t = min(exp[r], got[r])
            rule_stats[r][0] += t
            rule_stats[r][1] += got[r] - t
            rule_stats[r][2] += exp[r] - t
        t = sum((exp & got).values())
        tp += t
        fp += sum(got.values()) - t
        fn += sum(exp.values()) - t
        ok = exp == got
        passed += ok
        line_ok = exp_lines == got_lines
        if not ok or not line_ok:
            report.append((c["id"], "ok-rules/line-diff" if ok else "MISMATCH",
                           {f"{r}@{ln}": n for (r, ln), n in exp_lines.items()},
                           {f"{r}@{ln}": n for (r, ln), n in got_lines.items()}))
    print(f"cases: {len(cs)}; exact on supported rules: {passed}/{len(cs)} ({100 * passed / max(1, len(cs)):.1f}%)")
    print(f"findings: tp={tp} fp={fp} fn={fn}; precision={tp / max(1, tp + fp):.2f} recall={tp / max(1, tp + fn):.2f}")
    print("per rule (tp/fp/fn):", {r: tuple(v) for r, v in sorted(rule_stats.items())})
    (WORK / "report.json").write_text(json.dumps(report, indent=1, default=str))
    for cid, status, e, g in report:
        if status != "ok-rules/line-diff":
            print(f"  {cid}: {status} expected={e} got={g}")
    print(f"line-only differences: {sum(1 for r in report if r[1] == 'ok-rules/line-diff')} (see {WORK / 'report.json'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
