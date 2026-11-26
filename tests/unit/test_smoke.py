# SPDX-License-Identifier: Apache-2.0
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
from open_formal_cdc import __version__
from open_formal_cdc.cli import main


def test_version():
    assert __version__


def test_cli_runs():
    assert main([]) == 0
