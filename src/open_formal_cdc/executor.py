# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Executors: where Yosys and SBY run.

LocalExecutor runs on this machine. SshExecutor runs on a remote host: the work
directory is copied there and back with rsync; the remote path is the same as the
local one (same $HOME layout on both machines).
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    returncode: int
    output: str


class Executor:
    def sync_up(self, path: Path) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def sync_down(self, path: Path) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def run(self, command: str, cwd: Path, timeout: int) -> RunResult:  # pragma: no cover
        raise NotImplementedError


class LocalExecutor(Executor):
    def __init__(self, tools_bin: str | None = None):
        self.tools_bin = tools_bin

    def sync_up(self, path: Path) -> None:
        pass

    def sync_down(self, path: Path) -> None:
        pass

    def run(self, command: str, cwd: Path, timeout: int) -> RunResult:
        env = dict(os.environ)
        if self.tools_bin:
            env["PATH"] = os.path.expanduser(self.tools_bin) + os.pathsep + env["PATH"]
        p = subprocess.run(["bash", "-c", command], cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=timeout)
        return RunResult(p.returncode, p.stdout + p.stderr)


class SshExecutor(Executor):
    def __init__(self, host: str, key: str | None = None,
                 tools_bin: str = "~/Tools/oss-cad-suite/bin", connect_timeout: int = 8):
        self.host = host
        self.key = os.path.expanduser(key) if key else None
        self.tools_bin = tools_bin
        self.connect_timeout = connect_timeout

    def _ssh(self) -> list[str]:
        cmd = ["ssh", "-o", f"ConnectTimeout={self.connect_timeout}", "-o", "BatchMode=yes"]
        if self.key:
            cmd += ["-i", self.key]
        return cmd

    # SBY intermediate files that are not needed back on this machine
    DOWN_EXCLUDE = ["model/", "src/", "*.smt2", "*.aig", "*.aim", "*.ywa", "*.il", "*.btor"]

    def _rsync(self, src: str, dst: str, exclude: list[str] | None = None) -> None:
        e = " ".join(shlex.quote(a) for a in self._ssh())
        ex = [f"--exclude={x}" for x in exclude or []]
        subprocess.run(["rsync", "-az", "--delete", *ex, "-e", e, src, dst], check=True,
                       capture_output=True, text=True)

    def _remote(self, path: Path) -> str:
        return f"{self.host}:{shlex.quote(str(path))}"

    def sync_up(self, path: Path) -> None:
        subprocess.run(self._ssh() + [self.host, f"mkdir -p {shlex.quote(str(path))}"],
                       check=True, capture_output=True, text=True)
        self._rsync(f"{path}/", self._remote(path) + "/")

    def sync_down(self, path: Path) -> None:
        # --delete with excludes keeps local files that match the excludes (rtl/ is local)
        self._rsync(self._remote(path) + "/", f"{path}/", self.DOWN_EXCLUDE)

    def run(self, command: str, cwd: Path, timeout: int) -> RunResult:
        remote = (f"export PATH={self.tools_bin}:$PATH; cd {shlex.quote(str(cwd))} && "
                  f"timeout {int(timeout)} bash -c {shlex.quote(command)}")
        p = subprocess.run(self._ssh() + [self.host, remote], capture_output=True, text=True,
                           timeout=timeout + 60)
        return RunResult(p.returncode, p.stdout + p.stderr)


def make_executor(spec: str | None) -> Executor:
    """'local' or None: run locally; 'ssh:user@host[:keyfile]': run remotely."""
    if not spec or spec == "local":
        return LocalExecutor(os.environ.get("OFCDC_TOOLS_BIN"))
    if spec.startswith("ssh:"):
        host, _, key = spec[4:].partition(":")
        return SshExecutor(host, key or None)
    raise ValueError(f"unknown executor '{spec}'")
