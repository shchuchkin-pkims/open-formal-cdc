# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
"""Structural CDC analysis on the Yosys netlist."""

from .analysis import Structure, StructCrossing, analyze, to_config  # noqa: F401
from .graph import Graph  # noqa: F401
