# -*- coding: utf-8 -*-
"""Tests for core/utils.py

Covers the settings based paths, the artist lookup and the discovery of
sequences, shots, assets and USD files on a temporary file system.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import os
from pathlib import Path

# pytest modules
import pytest

# atlas modules
from atlas_manager.plugins.batcher.core import utils


def _touch(path):
    """Create an empty file and its parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path

# endregion

# ==========

# region Fixtures

@pytest.fixture
def shot_root(tmp_path, monkeypatch):
    """Use a temporary shot root and OS independent relative folders."""
    root = tmp_path / "05_SHOT"
    root.mkdir()
    monkeypatch.setenv("ATLAS_SHOT_ROOT", str(root))
    # the production values use Windows separators
    monkeypatch.setattr(utils, "relative_usd_path", lambda: os.path.join("rdr", "houdini", "live"))
    monkeypatch.setattr(utils, "relative_render_path", lambda: os.path.join("rdr", "houdini", "render"))
    return root


@pytest.fixture
def asset_root(tmp_path, monkeypatch):
    """Use a temporary asset root."""
    root = tmp_path / "04_ASSET"
    root.mkdir()
    monkeypatch.setenv("ATLAS_ASSET_ROOT", str(root))
    return root

# endregion

# ==========

# region Settings Helpers

def test_user_maps_the_machine_name(monkeypatch):
    monkeypatch.setattr(utils.platform, "node", lambda: "PC01")
    assert utils.user() == "alice"


def test_user_is_unknown_for_an_unlisted_machine(monkeypatch):
    monkeypatch.setattr(utils.platform, "node", lambda: "SOMEONE-ELSE")
    assert utils.user() == "unknown"


def test_paths_and_executables_come_from_the_settings(settings):
    assert utils.shotpath() == settings["ATLAS_SHOT_ROOT"]
    assert utils.husk_path() == settings["HUSK_PATH"]
    assert utils.hython_path() == settings["HYTHON_PATH"]
    assert utils.tractor_spool_path() == settings["TRACTOR_SPOOL_PATH"]


def test_missing_settings_raise_an_explicit_error(empty_env):
    with pytest.raises(RuntimeError, match="ATLAS_SHOT_ROOT"):
        utils.shotpath()
    with pytest.raises(RuntimeError, match="HUSK_PATH"):
        utils.husk_path()


def test_relative_paths_are_the_expected_folders():
    assert utils.relative_usd_path() == "rdr\\houdini\\live"
    assert utils.relative_render_path() == "rdr\\houdini\\render"

# endregion

# ==========

# region Render Versioning

def test_next_render_version_starts_at_v001(tmp_path):
    assert utils.get_next_render_version(tmp_path, "shot") == tmp_path / "shot" / "v001"


def test_next_render_version_skips_existing_versions(tmp_path):
    (tmp_path / "shot" / "v001").mkdir(parents=True)
    (tmp_path / "shot" / "v002").mkdir(parents=True)
    assert utils.get_next_render_version(tmp_path, "shot") == tmp_path / "shot" / "v003"

# endregion

# ==========

# region Shot Discovery

def test_sequences_lists_entries_and_folders(shot_root):
    (shot_root / "SEQ_010").mkdir()
    (shot_root / "SEQ_020").mkdir()
    _touch(shot_root / "notes.txt")
    names, paths = utils.sequences()
    assert sorted(names) == ["SEQ_010", "SEQ_020", "notes.txt"]
    assert sorted(paths) == sorted([str(shot_root / "SEQ_010"), str(shot_root / "SEQ_020")])


def test_shots_keeps_only_shot_folders_sorted(shot_root):
    sequence = shot_root / "SEQ_010"
    for name in ("seq010sh020", "seq010sh010", "references"):
        (sequence / name).mkdir(parents=True)
    _touch(sequence / "seq010sh030")
    names, paths = utils.shots(str(sequence))
    assert names == ["sh010", "sh020"]
    assert paths == [str(sequence / "seq010sh010"), str(sequence / "seq010sh020")]


def test_shots_of_a_missing_sequence_are_empty(shot_root):
    assert utils.shots(str(shot_root / "SEQ_999")) == ([], [])


def test_solve_path_builds_the_shot_folder(shot_root):
    assert utils.solve_path("SEQ_010", "sh020") == str(shot_root / "SEQ_010" / "seq010sh020")


def test_usd_path_lists_usd_and_usda_files(shot_root):
    live = shot_root / "SEQ_010" / "seq010sh020" / "rdr" / "houdini" / "live"
    _touch(live / "b.usda")
    _touch(live / "a.usd")
    _touch(live / "ignore.exr")
    names, paths = utils.usd_path("SEQ_010", "sh020")
    assert sorted(names) == ["a.usd", "b.usda"]
    assert sorted(paths) == sorted([str(live / "a.usd"), str(live / "b.usda")])


def test_usd_path_raises_when_the_folder_is_missing(shot_root):
    with pytest.raises(FileNotFoundError):
        utils.usd_path("SEQ_010", "sh020")


def test_render_path_creates_the_folder(shot_root):
    result = utils.render_path("SEQ_010", "sh020")
    assert Path(result).is_dir()
    assert result.endswith(os.path.join("rdr", "houdini", "render"))

# endregion

# ==========

# region Asset Discovery

def test_assets_finds_folders_containing_rdr_sorted(asset_root):
    (asset_root / "00_CHR" / "villain" / "rdr").mkdir(parents=True)
    (asset_root / "00_CHR" / "group" / "hero" / "rdr").mkdir(parents=True)
    (asset_root / "00_CHR" / "no_render").mkdir(parents=True)
    names, paths = utils.assets("Chara")
    assert names == ["hero", "villain"]
    assert paths == [asset_root / "00_CHR" / "group" / "hero", asset_root / "00_CHR" / "villain"]


def test_assets_uses_the_folder_of_each_type(asset_root):
    (asset_root / "01_PROP" / "lamp" / "rdr").mkdir(parents=True)
    (asset_root / "02_SET" / "forest" / "rdr").mkdir(parents=True)
    assert utils.assets("Prop")[0] == ["lamp"]
    assert utils.assets("Set")[0] == ["forest"]


def test_assets_returns_none_without_result(asset_root):
    assert utils.assets("Chara") is None  # folder missing
    (asset_root / "00_CHR" / "empty").mkdir(parents=True)
    assert utils.assets("Chara") is None  # no rdr folder
    assert utils.assets("Unknown") is None  # unknown type


def test_usd_path_lookdev_lists_usd_files_recursively(tmp_path):
    asset = tmp_path / "rani"
    live = asset / "rdr" / "houdini" / "live"
    _touch(live / "b.usd")
    _touch(live / "a.usda")
    _touch(live / "sub" / "c.usdc")
    _touch(live / "readme.txt")
    result = utils.usd_path_lookdev(asset)
    assert result is not None
    names, paths = result
    assert names == ["a.usda", "b.usd", "c.usdc"]
    assert paths == [live / "a.usda", live / "b.usd", live / "sub" / "c.usdc"]


def test_usd_path_lookdev_returns_none_without_result(tmp_path):
    assert utils.usd_path_lookdev(tmp_path / "missing") is None
    (tmp_path / "asset" / "rdr" / "houdini" / "live").mkdir(parents=True)
    assert utils.usd_path_lookdev(tmp_path / "asset") is None  # no USD file

# endregion
