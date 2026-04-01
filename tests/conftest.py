"""Shared fixtures for Agent Harmony test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure runtime/harmony is importable
RUNTIME_DIR = str(Path(__file__).resolve().parent.parent / "runtime")
if RUNTIME_DIR not in sys.path:
    sys.path.insert(0, RUNTIME_DIR)
