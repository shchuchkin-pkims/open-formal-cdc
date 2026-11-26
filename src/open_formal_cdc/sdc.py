# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Subset of SDC: clocks, asynchronous clock groups, port domains.

Supported commands (never executed as Tcl, only parsed):
  create_clock -name <id> -period <ns> [get_ports <port>]      (port optional: virtual clock)
  create_generated_clock -name <id> -source <clk> -divide_by <n> [get_pins|get_nets <x>]
  set_clock_groups -asynchronous -group {..} -group {..} ...
  set_input_delay  -clock <clk> <ns> [get_ports <ports>]
  set_output_delay -clock <clk> <ns> [get_ports <ports>]
Anything else is reported as unsupported.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SdcClock:
    name: str
    period: float | None
    port: str | None              # None: virtual clock
    source: str | None = None     # generated clock: master clock
    divide_by: int | None = None
    target: str | None = None     # generated clock: net or pin


@dataclass
class Sdc:
    clocks: list[SdcClock] = field(default_factory=list)
    async_groups: list[list[str]] = field(default_factory=list)
    input_clock: dict[str, str] = field(default_factory=dict)
    output_clock: dict[str, str] = field(default_factory=dict)
    unsupported: list[str] = field(default_factory=list)

    def domain_map(self) -> dict[str, str]:
        """Clock -> domain. Clocks in different asynchronous groups are different domains;
        without set_clock_groups all clocks are related (one domain), as in timing analysis.
        A clock not listed in any group forms its own domain only if groups exist."""
        names = [c.name for c in self.clocks]
        if not self.async_groups:
            return {n: "sync0" for n in names}
        dom = {}
        for i, grp in enumerate(self.async_groups):
            for n in grp:
                dom[n] = f"g{i}"
        for n in names:
            dom.setdefault(n, f"solo_{n}")
        return dom


def _tokens(line: str) -> list[str]:
    line = line.replace("[", " [ ").replace("]", " ] ").replace("{", " { ").replace("}", " } ")
    return shlex.split(line, posix=False)


def _bracket(tokens: list[str], i: int) -> tuple[list[str], int]:
    """Parse '[ get_ports a b ]' or '{ a b }' or a bare word at tokens[i]."""
    if tokens[i] == "[":
        j = tokens.index("]", i)
        return [x for x in tokens[i + 2:j] if x not in "{}"], j + 1
    if tokens[i] == "{":
        j = tokens.index("}", i)
        return tokens[i + 1:j], j + 1
    return [tokens[i]], i + 1


def parse_sdc(text: str) -> Sdc:
    s = Sdc()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        t = _tokens(line)
        cmd, i = t[0], 1
        opts: dict[str, list[str]] = {}
        args: list[str] = []
        groups: list[list[str]] = []
        while i < len(t):
            if t[i].startswith("-") and not re.match(r"^-?\d", t[i]):
                key = t[i]
                if key in ("-asynchronous", "-physically_exclusive", "-logically_exclusive", "-add"):
                    opts[key] = []
                    i += 1
                    continue
                val, i = _bracket(t, i + 1)
                if key == "-group":
                    groups.append(val)
                else:
                    opts[key] = val
            else:
                val, i = _bracket(t, i)
                args += val
        if cmd == "create_clock":
            s.clocks.append(SdcClock(opts["-name"][0], float(opts["-period"][0]) if "-period" in opts else None,
                                     args[0] if args else None))
        elif cmd == "create_generated_clock":
            s.clocks.append(SdcClock(opts["-name"][0], None, None, opts.get("-source", [None])[0],
                                     int(opts["-divide_by"][0]) if "-divide_by" in opts else None,
                                     args[0] if args else None))
        elif cmd == "set_clock_groups" and "-asynchronous" in opts:
            s.async_groups += groups
        elif cmd == "set_input_delay":
            for p in args[1:] if args and re.match(r"^-?[\d.]+$", args[0]) else args:
                s.input_clock[p] = opts["-clock"][0]
        elif cmd == "set_output_delay":
            for p in args[1:] if args and re.match(r"^-?[\d.]+$", args[0]) else args:
                s.output_clock[p] = opts["-clock"][0]
        else:
            s.unsupported.append(line)
    return s


def load_sdc(path: str | Path) -> Sdc:
    return parse_sdc(Path(path).read_text(encoding="utf-8"))
