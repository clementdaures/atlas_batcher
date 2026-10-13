# -*- coding: utf-8 -*-
"""Shared pytest fixtures for the Atlas Batcher tests

Makes the package importable under its production name
(`atlas_manager.plugins.batcher`) without Atlas Manager, and isolates every
test from the real `.env` file and from the host environment. Neither Houdini,
Tractor nor PySide6 is needed to run the tests.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import os
import sys
import types
from pathlib import Path

# pytest modules
import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "atlas_batcher"

FAKE_SETTINGS = {
    "TRACTOR_HOST": "http://tractor.test",
    "TRACTOR_USER": "tester",
    "TRACTOR_PASS": "secret",
    "TRACTOR_ROOMS": "01,02",
    "ATLAS_SHOT_ROOT": "/fake/shots",
    "ATLAS_ASSET_ROOT": "/fake/assets",
    "HUSK_PATH": r"C:\fake\bin\husk.exe",
    "HYTHON_PATH": r"C:\fake\bin\hython.exe",
    "TRACTOR_SPOOL_PATH": r"C:\fake\bin\tractor-spool.bat",
    "ATLAS_USER_MAP": "PC01:alice,PC02:bob",
}

# endregion

# ==========

# region Package Alias

def _install_package_alias():
    """Expose src/atlas_batcher as atlas_manager.plugins.batcher."""
    for name in ("atlas_manager", "atlas_manager.plugins"):
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules.setdefault(name, module)
    batcher = types.ModuleType("atlas_manager.plugins.batcher")
    batcher.__path__ = [str(PACKAGE_DIR)]
    sys.modules["atlas_manager.plugins.batcher"] = batcher
    sys.modules["atlas_manager.plugins"].batcher = batcher


_install_package_alias()

# endregion

# ==========

# region Fixtures

@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Point the loader to a fake .env file and clean the environment.

    Yields:
        Path: Path of the fake .env file.
    """
    from atlas_manager.plugins.batcher.core import env

    saved = dict(os.environ)
    for key in list(FAKE_SETTINGS) + [env.ENV_PATH_VARIABLE]:
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / "test.env"
    lines = ["# fake settings for the tests"]
    lines += [f"{key}={value}" for key, value in FAKE_SETTINGS.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setenv(env.ENV_PATH_VARIABLE, str(env_file))
    monkeypatch.setattr(env, "_loaded", False)
    yield env_file

    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def empty_env(tmp_path, monkeypatch):
    """Make every setting missing (no .env file found, nothing in os.environ)."""
    from atlas_manager.plugins.batcher.core import env

    for key in FAKE_SETTINGS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(env.ENV_PATH_VARIABLE, str(tmp_path / "missing.env"))
    monkeypatch.setattr(env, "_loaded", False)


@pytest.fixture
def settings():
    """Return a copy of the fake settings."""
    return dict(FAKE_SETTINGS)

# endregion
