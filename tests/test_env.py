# -*- coding: utf-8 -*-
"""Tests for core/env.py

Covers the .env parsing, the file lookup, the precedence of the real
environment variables and the typed accessors.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import os

# pytest modules
import pytest

# atlas modules
from atlas_manager.plugins.batcher.core import env

# endregion

# ==========

# region Parsing

def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_key_values(tmp_path):
    path = _write(tmp_path / "a.env", "A=1\nB=two words\n")
    assert env.parse_env_file(path) == {"A": "1", "B": "two words"}


def test_parse_ignores_comments_blank_lines_and_lines_without_equal(tmp_path):
    path = _write(tmp_path / "a.env", "# comment\n\nNOT_A_SETTING\nA=1\n")
    assert env.parse_env_file(path) == {"A": "1"}


def test_parse_accepts_export_prefix(tmp_path):
    path = _write(tmp_path / "a.env", "export A=1\n")
    assert env.parse_env_file(path) == {"A": "1"}


def test_parse_strips_matching_quotes_only(tmp_path):
    path = _write(tmp_path / "a.env", "A=\"x y\"\nB='z'\nC=\"odd'\n")
    assert env.parse_env_file(path) == {"A": "x y", "B": "z", "C": "\"odd'"}


def test_parse_keeps_backslashes(tmp_path):
    path = _write(tmp_path / "a.env", "P=\\\\server\\share\\05_SHOT\n")
    assert env.parse_env_file(path)["P"] == "\\\\server\\share\\05_SHOT"


def test_parse_value_may_contain_equal_sign(tmp_path):
    path = _write(tmp_path / "a.env", "MAP=A=b,C=d\n")
    assert env.parse_env_file(path)["MAP"] == "A=b,C=d"


def test_parse_handles_utf8_bom(tmp_path):
    path = tmp_path / "a.env"
    path.write_bytes(b"\xef\xbb\xbfA=1\n")
    assert env.parse_env_file(path) == {"A": "1"}

# endregion

# ==========

# region File Lookup

def test_find_env_file_uses_custom_path(isolated_env):
    assert env.find_env_file() == isolated_env


def test_find_env_file_custom_path_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv(env.ENV_PATH_VARIABLE, str(tmp_path / "nope.env"))
    assert env.find_env_file() is None


def test_find_env_file_searches_package_parents(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    fake_module = repo / "src" / "pkg" / "core" / "env.py"
    fake_module.parent.mkdir(parents=True)
    (repo / ".env").write_text("A=1\n", encoding="utf-8")
    monkeypatch.delenv(env.ENV_PATH_VARIABLE)
    monkeypatch.setattr(env, "__file__", str(fake_module))
    assert env.find_env_file() == (repo / ".env").resolve()


def test_find_env_file_returns_none_when_absent(tmp_path, monkeypatch):
    fake_module = tmp_path / "a" / "b" / "c" / "core" / "env.py"
    fake_module.parent.mkdir(parents=True)
    monkeypatch.delenv(env.ENV_PATH_VARIABLE)
    monkeypatch.setattr(env, "__file__", str(fake_module))
    assert env.find_env_file() is None

# endregion

# ==========

# region Loading

def test_load_env_fills_environment(settings):
    env.load_env()
    assert os.environ["TRACTOR_HOST"] == settings["TRACTOR_HOST"]


def test_load_env_never_overrides_existing_variables(monkeypatch):
    monkeypatch.setenv("TRACTOR_HOST", "http://from-environment")
    assert env.get("TRACTOR_HOST") == "http://from-environment"


def test_load_env_reads_the_file_once_unless_forced(isolated_env):
    env.load_env()
    isolated_env.write_text("NEW_KEY=1\n", encoding="utf-8")
    env.load_env()
    assert env.get("NEW_KEY") is None
    env.load_env(force=True)
    assert env.get("NEW_KEY") == "1"


def test_load_env_without_file_does_nothing(empty_env):
    env.load_env()
    assert env.get("TRACTOR_HOST") is None

# endregion

# ==========

# region Accessors

def test_get_returns_default_when_missing_or_empty(monkeypatch):
    assert env.get("UNKNOWN_KEY", "fallback") == "fallback"
    monkeypatch.setenv("EMPTY_KEY", "")
    assert env.get("EMPTY_KEY", "fallback") == "fallback"


def test_require_returns_value(settings):
    assert env.require("TRACTOR_USER") == settings["TRACTOR_USER"]


def test_require_raises_with_the_key_name(empty_env):
    with pytest.raises(RuntimeError, match="TRACTOR_HOST"):
        env.require("TRACTOR_HOST")


def test_get_list_splits_and_strips(monkeypatch):
    monkeypatch.setenv("LIST_KEY", " 01, 02 ,,03 ")
    assert env.get_list("LIST_KEY") == ["01", "02", "03"]
    assert env.get_list("UNKNOWN_KEY") == []


def test_get_dict_parses_pairs(monkeypatch):
    assert env.get_dict("ATLAS_USER_MAP") == {"PC01": "alice", "PC02": "bob"}
    monkeypatch.setenv("PAIRS", "a=1;b=2;broken")
    assert env.get_dict("PAIRS", sep=";", pair_sep="=") == {"a": "1", "b": "2"}
    assert env.get_dict("UNKNOWN_KEY") == {}

# endregion
