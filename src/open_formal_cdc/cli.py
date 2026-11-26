# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""open-formal-cdc command line."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .executor import make_executor
from .flow import FlowError, run
from .report import text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="open-formal-cdc",
                                 description="Formal verification of clock domain crossings")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run the checks from a configuration file")
    r.add_argument("config", type=Path)
    r.add_argument("-o", "--out", type=Path,
                   help="output directory (default: build/<name> next to the configuration)")
    r.add_argument("-x", "--executor", default=os.environ.get("OFCDC_EXECUTOR", "local"),
                   help="local or ssh:user@host[:keyfile] (environment variable OFCDC_EXECUTOR)")
    r.add_argument("-j", "--parallel", type=int, default=8, help="SBY jobs in parallel")
    r.add_argument("--check", action="append", help="run only this check (repeatable)")
    r.add_argument("--models", help="comma-separated time models: ticks,clk2ff")
    g = sub.add_parser("cegar", help="refine explicit cut nets and confirm results on the full model")
    g.add_argument("config", type=Path)
    g.add_argument("-o", "--out", type=Path)
    g.add_argument("-x", "--executor", default=os.environ.get("OFCDC_EXECUTOR", "local"))
    g.add_argument("-j", "--parallel", type=int, default=8)
    g.add_argument("--check", action="append", required=True,
                   help="check with cuts or automatic en_stable/gray focus (exactly one)")
    g.add_argument("--models", help="comma-separated time models: ticks,clk2ff")
    g.add_argument("--rounds", type=int, default=6, help="maximum refinement runs before the full model")
    b = sub.add_parser("ablate", help="measure whether each assumption is necessary")
    b.add_argument("config", type=Path)
    b.add_argument("-o", "--out", type=Path)
    b.add_argument("-x", "--executor", default=os.environ.get("OFCDC_EXECUTOR", "local"))
    b.add_argument("-j", "--parallel", type=int, default=8)
    b.add_argument("--check", action="append", help="run only this check (repeatable)")
    b.add_argument("--models", help="comma-separated time models: ticks,clk2ff")
    a = sub.add_parser("analyze", help="structural analysis only: crossings and proposed checks")
    a.add_argument("config", type=Path)
    a.add_argument("-o", "--out", type=Path)
    a.add_argument("-x", "--executor", default=os.environ.get("OFCDC_EXECUTOR", "local"))
    t = sub.add_parser("trace", help="table of signal values per step from a VCD trace")
    t.add_argument("vcd", type=Path)
    t.add_argument("signals", nargs="*", help="signal names (full or last component); all if omitted")
    args = ap.parse_args(argv)
    if args.cmd == "trace":
        from .vcdtab import table
        print(table(args.vcd, args.signals or None))
        return 0
    if args.cmd is None:
        ap.print_help()
        return 0
    if args.cmd == "analyze":
        return _analyze(args)
    try:
        cfg = load_config(args.config)
        if args.models:
            cfg.options.time_models = [m.strip() for m in args.models.split(",") if m.strip()]
        out = args.out or (cfg.path.parent / "build" / cfg.path.stem)
        if args.cmd == "cegar":
            from .cegar import cegar
            reports = cegar(cfg, out, make_executor(args.executor), args.parallel, args.check,
                            max_rounds=args.rounds, log=lambda s: print(s, file=sys.stderr))
            for r in reports:
                print(f"{r.variant}/{r.check}: {r.status}; abstract_cex={r.abstract_cex}; {r.detail}")
            print(f"\nCEGAR: {out.resolve() / 'cegar.json'}")
            return int(any(r.status in ("unknown", "error") for r in reports))
        if args.cmd == "ablate":
            from .ablate import ablate
            effects = ablate(cfg, out, make_executor(args.executor), args.parallel, args.check,
                             log=lambda s: print(s, file=sys.stderr))
            for e in effects:
                print(f"{e.assumption}: {e.classification}")
            print(f"\nAblation: {out.resolve() / 'ablation.json'}")
            return 0
        result = run(cfg, out, make_executor(args.executor), args.parallel, args.check,
                       log=lambda s: print(s, file=sys.stderr))
    except (ConfigError, FlowError, FileNotFoundError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(text(result, cfg.options.time_models))
    print(f"\nResults: {out.resolve() / 'results.json'}\nModel:   {out.resolve() / 'cdc_model.json'}")
    return 1 if result.mismatches else 0


def _analyze(args) -> int:
    from .flow import frontend, structural
    from .report import structure_text
    try:
        cfg = load_config(args.config)
        out = args.out or (cfg.path.parent / "build" / cfg.path.stem)
        frontend(cfg, out, make_executor(args.executor), log=lambda s: print(s, file=sys.stderr))
        structures, crossings_v, checks_v, assumptions_v = structural(cfg, out.resolve(), cfg.variants)
    except (ConfigError, FlowError, FileNotFoundError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for v in cfg.variants:
        print(f"== variant {v.name}")
        print(structure_text(structures.get(v.name), checks_v[v.name], assumptions_v[v.name]))
    print(f"\nStructure: {out.resolve()}/<variant>/structure.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
