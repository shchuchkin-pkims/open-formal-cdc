# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Yosys netlist (write_json) after flatten: ports and nets of the top module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Port:
    name: str
    direction: str   # input | output | inout
    width: int


class Netlist:
    def __init__(self, data: dict, top: str):
        mods = data.get("modules", {})
        if top not in mods:
            raise KeyError(f"module '{top}' not found in netlist (available: {', '.join(sorted(mods))})")
        self.top = top
        self._mod = mods[top]
        self.ports: dict[str, Port] = {
            n: Port(n, p["direction"], len(p["bits"])) for n, p in self._mod.get("ports", {}).items()
        }
        self.nets: dict[str, int] = {
            n: len(v["bits"]) for n, v in self._mod.get("netnames", {}).items()
        }

    @classmethod
    def load(cls, path: Path, top: str) -> "Netlist":
        return cls(json.loads(Path(path).read_text()), top)

    def net_width(self, name: str) -> int:
        if name not in self.nets:
            close = [n for n in self.nets if n.endswith(name.split(".")[-1])][:5]
            hint = f"; similar: {', '.join(close)}" if close else ""
            raise KeyError(f"net '{name}' not found in '{self.top}'{hint}")
        return self.nets[name]

    def inputs(self) -> list[Port]:
        return [p for p in self.ports.values() if p.direction == "input"]

    def outputs(self) -> list[Port]:
        return [p for p in self.ports.values() if p.direction == "output"]
