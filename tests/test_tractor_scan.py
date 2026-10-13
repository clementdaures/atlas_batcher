# -*- coding: utf-8 -*-
"""Tests for core/tractor_scan.py

Covers the settings, the three Tractor authentication methods, the blade
classification, the physical RAM query and the ping. The Tractor server, the
blade daemons and the ping command are replaced by fakes, so no network access
is needed.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import hashlib
import json
import time
import types
import urllib.error

# pytest modules
import pytest

# atlas modules
from atlas_manager.plugins.batcher.core import tractor_scan


def _md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def blade(name, **overrides):
    """Build the raw data of a responsive idle blade."""
    data = {
        "name": name, "t": time.time(), "nimby": "", "numcmd": 0,
        "ns": 4, "ncpu": 8, "cpu": 0.5, "mem": 31.94, "addr": f"{name}.farm", "profile": "default",
    }
    data.update(overrides)
    return data

# endregion

# ==========

# region Fixtures

@pytest.fixture
def farm(monkeypatch):
    """Fake Tractor server, blade daemons and ping command.

    Returns:
        types.SimpleNamespace: State with blades, urls, handler, daemon, connections,
            ping_dead and ping_calls that tests can change.
    """
    state = types.SimpleNamespace(
        blades=[], urls=[], handler=None, daemon=None, connections=[], ping_dead=set(), ping_calls=[]
    )

    def default_handler(url):
        if "q=login" in url:
            return {"tsid": "abc123"}
        if "q=blades" in url:
            return {"blades": state.blades}
        raise AssertionError(f"unexpected url {url}")

    state.handler = default_handler

    class FakeResponse:
        def __init__(self, payload):
            self._body = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeOpener:
        def open(self, url, timeout=None):
            state.urls.append(url)
            result = state.handler(url)
            if isinstance(result, Exception):
                raise result
            return FakeResponse(result)

    class FakeSocket:
        def __init__(self, payload):
            self._chunks = [payload, b""]
            self.sent = b""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def sendall(self, data):
            self.sent += data

        def settimeout(self, value):
            pass

        def recv(self, size):
            return self._chunks.pop(0) if self._chunks else b""

    def fake_create_connection(address, timeout=None):
        state.connections.append(address)
        if state.daemon is None:
            raise OSError("blade daemon unreachable")
        return FakeSocket(b"HTTP/1.0 200 OK\r\n\r\n" + json.dumps(state.daemon).encode("utf-8"))

    def fake_run(cmd, **kwargs):
        state.ping_calls.append(cmd)
        return types.SimpleNamespace(returncode=1 if cmd[-1] in state.ping_dead else 0)

    monkeypatch.setattr(tractor_scan.urllib.request, "build_opener", lambda *args, **kwargs: FakeOpener())
    monkeypatch.setattr(tractor_scan.socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(tractor_scan.subprocess, "run", fake_run)
    return state

# endregion

# ==========

# region Settings

@pytest.mark.parametrize("key", ["TRACTOR_HOST", "TRACTOR_USER", "TRACTOR_PASS"])
def test_missing_setting_raises_an_explicit_error(farm, empty_env, monkeypatch, key, settings):
    for name in ("TRACTOR_HOST", "TRACTOR_USER", "TRACTOR_PASS"):
        if name != key:
            monkeypatch.setenv(name, settings[name])
    with pytest.raises(RuntimeError, match=key):
        tractor_scan.run_scan(do_ping=False)
    assert farm.urls == []  # nothing is requested before the settings are checked

# endregion

# ==========

# region Authentication

def test_direct_login_uses_the_user_and_host_from_the_settings(farm):
    tractor_scan.run_scan(do_ping=False)
    assert farm.urls[0] == "http://tractor.test/Tractor/monitor?q=login&user=tester"
    assert farm.urls[1] == "http://tractor.test/Tractor/monitor?q=blades&tsid=abc123"


def test_login_user_is_url_quoted(farm, monkeypatch):
    monkeypatch.setenv("TRACTOR_USER", "a b&c")
    tractor_scan.run_scan(do_ping=False)
    assert "user=a%20b%26c" in farm.urls[0]


def test_md5_challenge_login(farm):
    expected = _md5("nonce42" + _md5("secret"))

    def handler(url):
        if "q=blades" in url:
            assert "tsid=session2" in url
            return {"blades": []}
        return {"tsid": "session2"} if f"&c={expected}" in url else {"RC": "nonce42"}

    farm.handler = handler
    tractor_scan.run_scan(do_ping=False)
    assert f"&c={expected}" in farm.urls[1]


def test_md5_password_fallback_login(farm):
    def handler(url):
        if "q=blades" in url:
            return {"blades": []}
        return {"tsid": "session3"} if f"&c={_md5('secret')}" in url else {"unexpected": True}

    farm.handler = handler
    tractor_scan.run_scan(do_ping=False)
    assert any(f"&c={_md5('secret')}" in url for url in farm.urls)


def test_all_authentication_methods_failing(farm):
    farm.handler = lambda url: {"error": "denied"}
    with pytest.raises(RuntimeError, match="All auth methods failed"):
        tractor_scan.run_scan(do_ping=False)


def test_http_error_is_reported(farm):
    farm.handler = lambda url: urllib.error.HTTPError(url, 500, "error", {}, None)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        tractor_scan.run_scan(do_ping=False)


def test_unreachable_server_is_reported(farm):
    farm.handler = lambda url: urllib.error.URLError("connection refused")
    with pytest.raises(RuntimeError, match="Cannot reach"):
        tractor_scan.run_scan(do_ping=False)

# endregion

# ==========

# region Blade Classification

def test_blades_are_classified_by_state_and_sorted(farm):
    farm.blades = [
        blade("z-idle"),
        blade("a-idle"),
        blade("busy-01", numcmd=2),
        blade("nimby-01", nimby="Artist working"),
        blade("dead-01", t=0),
    ]
    by_state, ping = tractor_scan.run_scan(do_ping=False)
    assert set(by_state) == {"idle", "busy", "nimby", "unresponsive"}
    assert [b["name"] for b in by_state["idle"]] == ["a-idle", "z-idle"]
    assert [b["name"] for b in by_state["busy"]] == ["busy-01"]
    assert [b["name"] for b in by_state["nimby"]] == ["nimby-01"]
    assert [b["name"] for b in by_state["unresponsive"]] == ["dead-01"]
    assert ping == {}


def test_unresponsive_wins_over_nimby_and_busy(farm):
    farm.blades = [blade("old", t=0, nimby="x", numcmd=3)]
    by_state, _ = tractor_scan.run_scan(do_ping=False)
    assert [b["name"] for b in by_state["unresponsive"]] == ["old"]


def test_blade_entry_fields(farm):
    farm.blades = [blade("a-01", numcmd=1, owners=["alice"], note="  rendering  ")]
    entry = tractor_scan.run_scan(do_ping=False)[0]["busy"][0]
    assert entry["name"] == "a-01"
    assert entry["slots"] == 4 and entry["cores"] == 8 and entry["load"] == 0.5
    assert entry["mem_gb"] == 31.9
    assert entry["owners"] == ["alice"]
    assert entry["note"] == "rendering"
    assert entry["addr"] == "a-01.farm"
    assert entry["raw"]["profile"] == "default"


def test_missing_fields_fall_back_to_placeholders(farm):
    farm.blades = [{"hnm": "alt-name", "t": time.time()}]
    entry = tractor_scan.run_scan(do_ping=False)[0]["idle"][0]
    assert entry["name"] == "alt-name"
    assert entry["slots"] == entry["cores"] == entry["load"] == entry["mem_gb"] == "?"
    assert entry["owners"] == []


def test_blades_can_be_returned_under_the_data_key(farm):
    farm.handler = lambda url: {"tsid": "t"} if "q=login" in url else {"data": [blade("a-01")]}
    assert len(tractor_scan.run_scan(do_ping=False)[0]["idle"]) == 1


def test_empty_farm(farm):
    by_state, ping = tractor_scan.run_scan(do_ping=True)
    assert all(blades == [] for blades in by_state.values())
    assert ping == {}

# endregion

# ==========

# region Physical RAM

def test_physical_ram_is_read_from_the_blade_daemon(farm):
    farm.daemon = {"memPhys": 63.8}
    farm.blades = [blade("a-01", lp=9100), blade("b-01"), blade("dead-01", t=0)]
    by_state, _ = tractor_scan.run_scan(do_ping=False)
    assert [b["mem_phys_gb"] for b in by_state["idle"]] == [63.8, 63.8]
    assert by_state["unresponsive"][0]["mem_phys_gb"] is None  # dead blades are not queried
    assert ("a-01.farm", 9100) in farm.connections  # custom port
    assert ("b-01.farm", 9005) in farm.connections  # default port


def test_physical_ram_is_none_when_the_daemon_is_unreachable(farm):
    farm.blades = [blade("a-01")]
    assert tractor_scan.run_scan(do_ping=False)[0]["idle"][0]["mem_phys_gb"] is None


def test_blade_without_address_is_not_queried(farm):
    farm.daemon = {"memPhys": 10}
    farm.blades = [blade("a-01", addr="")]
    by_state, _ = tractor_scan.run_scan(do_ping=False)
    assert by_state["idle"][0]["mem_phys_gb"] is None
    assert farm.connections == []

# endregion

# ==========

# region Ping

def test_ping_covers_the_active_blades_only(farm):
    farm.blades = [blade("idle-01"), blade("busy-01", numcmd=1), blade("nimby-01", nimby="x"), blade("dead-01", t=0)]
    _, ping = tractor_scan.run_scan(do_ping=True)
    assert ping == {"idle-01": True, "busy-01": True, "nimby-01": True}


def test_unreachable_blade_is_reported_as_down(farm):
    farm.ping_dead = {"idle-02"}
    farm.blades = [blade("idle-01"), blade("idle-02")]
    _, ping = tractor_scan.run_scan(do_ping=True)
    assert ping == {"idle-01": True, "idle-02": False}


def test_ping_command_targets_the_blade_name(farm):
    farm.blades = [blade("idle-01")]
    tractor_scan.run_scan(do_ping=True)
    assert farm.ping_calls[0][0] == "ping"
    assert farm.ping_calls[0][-1] == "idle-01"


def test_ping_is_skipped_when_disabled(farm):
    farm.blades = [blade("idle-01")]
    assert tractor_scan.run_scan(do_ping=False)[1] == {}
    assert farm.ping_calls == []

# endregion
