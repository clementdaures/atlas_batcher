# -*- coding: utf-8 -*-
"""Tractor farm scanner

Connects to a Tractor instance, retrieves the blade states, and optionally
pings the blades. The Tractor host and credentials are read from the .env file
through the env module.

Public API: run_scan(do_ping) -> (by_state, ping_results)

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import urllib.request
import urllib.parse
import urllib.error
import json
import hashlib
import http.cookiejar
import logging
import sys
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

# atlas modules
from atlas_manager.plugins.batcher.core import env

# TRACTOR_HOST, TRACTOR_USER and TRACTOR_PASS are read from the .env file
HTTP_TIMEOUT    = 10
PING_COUNT      = 1
PING_TIMEOUT    = 1000   # ms
PING_WORKERS    = 64
BLADE_TIMEOUT   = 300    # seconds before a blade is considered unresponsive

log = logging.getLogger("tractor_scanner")
log.addHandler(logging.NullHandler())

# endregion

# ==========

# region Farm Scan

def run_scan(do_ping: bool = True) -> tuple[dict[str, list[dict]], dict[str, bool]]:
    """Run a full farm scan.

    Authenticates to Tractor, fetches all the blades, classifies them by state,
    fetches the physical RAM of the active blades, and optionally pings them.

    Args:
        do_ping (bool): Ping the active blades.

    Returns:
        tuple[dict[str, list[dict]], dict[str, bool]]: A pair made of:
            by_state: {"idle": [...], "busy": [...], "nimby": [...], "unresponsive": [...]}.
                Each blade dict contains name, state, slots, cores, load, mem_gb,
                mem_phys_gb, profile, nimby, numcmd, owners, note, addr and raw.
            ping_results: {hostname: bool}, empty if do_ping is False.

    Raises:
        RuntimeError: If a setting is missing, Tractor cannot be reached, or all
            the authentication methods fail.
    """

    # ----- Settings (.env) -----
    tractor_host = env.require("TRACTOR_HOST")
    tractor_user = env.require("TRACTOR_USER")
    tractor_pass = env.require("TRACTOR_PASS")

    # ----- Auth -----
    jar    = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def _get(url: str) -> dict:
        """HTTP GET returning the parsed JSON.

        Args:
            url (str): URL to request.

        Returns:
            dict: Parsed JSON response.

        Raises:
            RuntimeError: On an HTTP error or if the URL cannot be reached.
        """
        try:
            with opener.open(url, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} on {url}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach {url}: {e.reason}") from e

    def _md5(s: str) -> str:
        """Return the MD5 hex digest of a string.

        Args:
            s (str): String to hash.

        Returns:
            str: MD5 hex digest.
        """
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    base = f"{tractor_host}/Tractor/monitor"

    # Try login — supports direct tsid, MD5 challenge, and MD5 password fallback
    data = _get(f"{base}?q=login&user={urllib.parse.quote(tractor_user)}")

    if "tsid" not in data:
        nonce = data.get("RC") or data.get("nonce") or data.get("challenge")
        if nonce:
            data = _get(
                f"{base}?q=login&user={urllib.parse.quote(tractor_user)}"
                f"&c={_md5(str(nonce) + _md5(tractor_pass))}"
            )
        if "tsid" not in data:
            data = _get(
                f"{base}?q=login&user={urllib.parse.quote(tractor_user)}"
                f"&c={_md5(tractor_pass)}"
            )
        if "tsid" not in data:
            raise RuntimeError(f"All auth methods failed. Last response: {data}")

    tsid = data["tsid"]
    log.info(f"Authenticated — tsid: {tsid}")

    # ----- Fetch & classify blades -----
    raw_data = _get(f"{tractor_host}/Tractor/monitor?q=blades&tsid={tsid}")
    raw_blades = raw_data.get("blades") or raw_data.get("data") or (raw_data if isinstance(raw_data, list) else [])
    log.info(f"{len(raw_blades)} blade(s) returned")

    def _classify(b: dict) -> str:
        """Determine the state of a blade from its raw Tractor data.

        Args:
            b (dict): Raw blade data.

        Returns:
            str: 'unresponsive', 'nimby', 'busy' or 'idle'.
        """
        if (time.time() - float(b.get("t") or 0)) > BLADE_TIMEOUT:
            return "unresponsive"
        if b.get("nimby", "").strip():
            return "nimby"
        if int(b.get("numcmd") or 0) > 0:
            return "busy"
        return "idle"

    by_state: dict[str, list[dict]] = {"idle": [], "busy": [], "nimby": [], "unresponsive": []}

    for b in raw_blades:
        mem = b.get("mem") or b.get("physmem") or "?"
        entry = {
            "name":       b.get("name") or b.get("hnm") or b.get("hostname") or "?",
            "state":      _classify(b),
            "slots":      b.get("ns")    or b.get("numslots") or "?",
            "cores":      b.get("ncpu")  or b.get("numcpu")   or "?",
            "load":       b.get("cpu")   or b.get("loadavg")  or "?",
            "mem_gb":     round(float(mem), 1) if mem != "?" else "?",
            "mem_phys_gb": None,
            "profile":    b.get("profile", ""),
            "nimby":      b.get("nimby", ""),
            "numcmd":     b.get("numcmd", 0),
            "owners":     b.get("owners") or [],
            "note":       b.get("note", "").strip(),
            "addr":       b.get("addr", ""),
            "raw":        b,
        }
        by_state[entry["state"]].append(entry)

    for lst in by_state.values():
        lst.sort(key=lambda x: x["name"])

    # ----- Physical RAM (parallel, blade daemon port 9005) -----
    active_blades = by_state["idle"] + by_state["busy"] + by_state["nimby"]

    def _fetch_mem(blade: dict) -> tuple[str, float | None]:
        """Query the blade daemon directly for its physical RAM.

        Args:
            blade (dict): Blade entry from the classified blades.

        Returns:
            tuple[str, float | None]: Blade name and physical RAM in GB, or None if unavailable.
        """
        name = blade["name"]
        addr = blade["raw"].get("addr", "")
        port = int(blade["raw"].get("lp") or 9005)
        if not addr:
            return name, None
        try:
            with socket.create_connection((addr, port), timeout=3) as s:
                s.sendall(f"GET /blade/status HTTP/1.0\r\nHost: {addr}\r\n\r\n".encode())
                s.settimeout(3)
                chunks = []
                try:
                    while True:
                        chunk = s.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                except socket.timeout:
                    pass
                body = b"".join(chunks).decode("utf-8", errors="replace")
                if "\r\n\r\n" in body:
                    body = body.split("\r\n\r\n", 1)[1].strip()
                data = json.loads(body)
                val = float(data.get("memPhys") or 0)
                return name, val or None
        except Exception:
            return name, None

    if active_blades:
        with ThreadPoolExecutor(max_workers=64) as pool:
            for name, val in pool.map(_fetch_mem, active_blades):
                if val:
                    for blade in active_blades:
                        if blade["name"] == name:
                            blade["mem_phys_gb"] = val
                            break

    # ----- Ping (parallel ICMP) -----
    ping_results: dict[str, bool] = {}

    if do_ping:
        ping_targets = [b["name"] for b in active_blades]

        def _ping(name: str) -> tuple[str, bool]:
            """Send a single ICMP ping.

            Args:
                name (str): Hostname to ping.

            Returns:
                tuple[str, bool]: Hostname and whether it is reachable.
            """
            try:
                if sys.platform == "win32":
                    cmd = ["ping", "-n", str(PING_COUNT), "-w", str(PING_TIMEOUT), name]
                else:
                    cmd = ["ping", "-c", str(PING_COUNT), "-W", str(max(1, PING_TIMEOUT // 1000)), name]
                r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=PING_TIMEOUT / 1000 + 2)
                return name, r.returncode == 0
            except Exception:
                return name, False

        with ThreadPoolExecutor(max_workers=PING_WORKERS) as pool:
            for name, alive in pool.map(_ping, ping_targets):
                ping_results[name] = alive

        alive_n = sum(ping_results.values())
        log.info(f"Ping done - {alive_n}/{len(ping_targets)} reachable")

    return by_state, ping_results

# endregion
