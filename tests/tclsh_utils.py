from __future__ import annotations

import shutil

import pytest


def require_tclsh() -> str:
    tclsh = shutil.which("tclsh")
    if tclsh is None:
        pytest.skip("tclsh is not installed")
    return tclsh
