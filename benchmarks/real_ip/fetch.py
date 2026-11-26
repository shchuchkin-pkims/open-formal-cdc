#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Fetch pinned open-source RTL used by the real-IP CDC benchmarks."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"
REPOS = {
    "riscv-dbg": ("https://github.com/pulp-platform/riscv-dbg.git",
                  "643607e19df3435cfd77cc56143e2637f5900a6e"),
    "common_cells": ("https://github.com/pulp-platform/common_cells.git",
                     "b5ec8905ed7828655155b0ae971023adf793c600"),
    "tech_cells_generic": ("https://github.com/pulp-platform/tech_cells_generic.git",
                           "55cb54513e2d426be5992d311cb9d5dbcad10c78"),
    "axi_spi_slave": ("https://github.com/pulp-platform/axi_spi_slave.git",
                      "b15bdd4126610e8ef01f3a3722be791f4dde9d4e"),
    "axi_slice_dc": ("https://github.com/pulp-platform/axi_slice_dc.git",
                     "fbfb22bd5ce999e74f2f97440df77c435bf22883"),
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def fetch(name: str, url: str, revision: str) -> None:
    dest = CACHE / name
    if dest.exists() and git("-C", str(dest), "rev-parse", "HEAD") == revision:
        print(f"{name}: {revision} already available")
        return
    if not dest.exists():
        git("clone", "--filter=blob:none", "--no-checkout", url, str(dest))
    git("-C", str(dest), "fetch", "--depth", "1", "origin", revision)
    git("-C", str(dest), "checkout", "--detach", revision)
    print(f"{name}: {revision}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="check revisions without downloading")
    args = ap.parse_args()
    if args.check:
        missing = []
        for name, (_, revision) in REPOS.items():
            dest = CACHE / name
            if not dest.exists() or git("-C", str(dest), "rev-parse", "HEAD") != revision:
                missing.append(name)
        if missing:
            print("Missing or different: " + ", ".join(missing))
            return 1
        print("All pinned sources are available")
        return 0
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, (url, revision) in REPOS.items():
        fetch(name, url, revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
