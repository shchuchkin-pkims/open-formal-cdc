# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Property templates: build a checker instance from a check in the configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Callable, Protocol


@dataclass
class Instance:
    """Template output: what goes into the wrapper."""
    lib_files: list[str]          # files from open_formal_cdc/lib
    verilog: str                  # instance text inside the wrapper
    asserts: list[str]            # assertion names in ofcdc_top (hierarchical)
    covers: list[str]             # cover names in ofcdc_top
    notes: list[str] = field(default_factory=list)
    script: list[str] = field(default_factory=list)   # Yosys commands in the design, after exposure


class Context(Protocol):
    """What the job builder gives a template (see jobs.py)."""
    def clock(self, name: str) -> str: ...          # domain clock signal in the wrapper
    def act(self, clock: str) -> str: ...           # domain is out of reset
    def init_done(self) -> str: ...                 # initial reset is over
    def match(self, pattern: str, exclude: list[str] | None = None) -> list[str]: ...  # nets by glob
    def dut_name(self, net: str) -> str: ...        # name of the net inside the design after exposure
    def known_nets(self) -> set[str]: ...
    def top_name(self) -> str: ...
    def data_inputs(self) -> list[str]: ...
    def input_ports(self) -> list[str]: ...
    def add_design(self, module: str, outputs: dict[str, str],
                   inputs: list[tuple[str, int]]) -> None: ...
    def edge(self, clock: str) -> str: ...          # active edge of a clock in this global step
    def model_param(self) -> str: ...               # wrapper localparam: 1 ticks, 0 clk2fflogic
    def signal(self, net: str) -> tuple[str, int]:  # wrapper signal for a design net, width
        ...


class TemplateError(ValueError):
    pass


Template = Callable[[str, dict[str, Any], Context], Instance]
REGISTRY: dict[str, Template] = {}


def register(name: str):
    def deco(fn: Template) -> Template:
        REGISTRY[name] = fn
        return fn
    return deco


def get(name: str) -> Template:
    if name not in REGISTRY:
        raise TemplateError(f"unknown template '{name}' (available: {', '.join(sorted(REGISTRY))})")
    return REGISTRY[name]


def lib_text(name: str) -> str:
    return resources.files("open_formal_cdc.lib").joinpath(name).read_text(encoding="utf-8")


def need(params: dict[str, Any], key: str, check: str) -> Any:
    if key not in params:
        raise TemplateError(f"check '{check}': missing parameter '{key}'")
    return params[key]


from . import async_nonew, clock_mux, en_stable, env, fifo, gray, handshake, hazard, meta, onechange, pulse, rdc_capture, reset_latency, reset_release, reset_sync, reset_value, rise_latency, settled  # noqa: E402,F401  template registration
