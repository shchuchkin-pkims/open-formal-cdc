# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Design reading: Yosys (yosys-slang) commands and the netlist script."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import Design


def sv_value(v: Any) -> str:
    """Parameter value for the yosys-slang -G option."""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def copy_sources(design: Design, dest: Path) -> list[str]:
    """Copy design sources to dest with unique names; return the file names."""
    dest.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for i, f in enumerate(design.files):
        if not f.is_file():
            raise FileNotFoundError(f"design file not found: {f}")
        name = f.name if f.name not in names else f"{i}_{f.name}"
        shutil.copy2(f, dest / name)
        names.append(name)
    return names


def read_commands(design: Design, files: list[str]) -> list[str]:
    """Yosys commands from reading the sources to a flat top module."""
    params = " ".join(f"-G {k}={sv_value(v)}" for k, v in design.params.items())
    extra = " ".join(design.slang_args)
    read = " ".join(x for x in ["read_slang", " ".join(files), f"--top {design.top}", params, extra] if x)
    return [read, f"hierarchy -top {design.top}", "proc", "flatten", "opt_clean"]


def frontend_script(design: Design, files: list[str], keep: list[str] | None = None) -> str:
    """Netlist for the structural analysis; modules in 'keep' (synchronizer cells) stay
    as black-box cells. Formal jobs still read the full design."""
    cmds = read_commands(design, files)
    if keep:     # yosys-slang elaborates flat; black-box the cells for the structure only
        cmds[0] += "".join(f" --blackboxed-module {m}" for m in keep)
    # same commands as the formal jobs: net names match (needed to place models)
    return "\n".join(cmds + ["write_json netlist.json", ""])
