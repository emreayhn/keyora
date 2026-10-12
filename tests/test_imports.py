"""Smoke test — tüm modüller import edilebiliyor mu (UI sözdizimi hataları dahil)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

MODULES = [
    "main",
    "core.crypto", "core.database", "core.vault", "core.backup", "core.health",
    "utils.clipboard", "utils.csv_io", "utils.password_gen", "utils.win_integration",
    "utils.importers",
    "ui.main_window", "ui.login_dialog", "ui.setup_dialog", "ui.settings_dialog",
    "ui.entry_dialog", "ui.history_dialog", "ui.generator_dialog", "ui.about_dialog",
    "ui.health_dialog", "ui.import_dialog",
    "ui.components.entry_card",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str):
    importlib.import_module(name)
