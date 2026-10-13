# -*- coding: utf-8 -*-
"""Environment settings loader for Atlas Batcher

Loads the private settings (Tractor host and credentials, storage roots,
install paths, artist machine map) from a `.env` file so that no sensitive
value is hardcoded in the source code. Only the standard library is used.

The `.env` file is searched in this order:
    1. The path stored in the ATLAS_BATCHER_ENV environment variable.
    2. A `.env` file in the package folder, in its parent folder, or in the
       repository root.

Values already present in os.environ always take precedence over the file.
Copy `.env.example` to `.env` and fill it in.

Author: Clement Daures
Website: clementdaures.com
Created: 2025

Example:
    from atlas_manager.plugins.batcher.core import env

    host = env.require("TRACTOR_HOST")
    rooms = env.get_list("TRACTOR_ROOMS")
"""

# region Imports & Config

# python modules
import os
from pathlib import Path
from typing import Dict, List, Optional

ENV_PATH_VARIABLE = "ATLAS_BATCHER_ENV"
ENV_FILE_NAME = ".env"

_loaded = False

# endregion

# ==========

# region Env Loader

def find_env_file() -> Optional[Path]:
    """Locate the `.env` file.

    Returns:
        Path | None: Path of the `.env` file, or None if no file is found.
    """
    custom = os.environ.get(ENV_PATH_VARIABLE)
    if custom:
        custom_path = Path(custom)
        return custom_path if custom_path.is_file() else None

    for folder in list(Path(__file__).resolve().parents)[1:4]:
        candidate = folder / ENV_FILE_NAME
        if candidate.is_file():
            return candidate
    return None


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a `.env` file.

    Blank lines and lines starting with '#' are ignored. Each other line must
    be KEY=VALUE, with an optional 'export ' prefix and optional surrounding
    quotes. Backslashes are kept as they are, so Windows paths can be written
    without escaping.

    Args:
        path (Path): Path of the `.env` file.

    Returns:
        Dict[str, str]: Settings found in the file.
    """
    values: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    return values


def load_env(force: bool = False) -> None:
    """Load the `.env` file into os.environ.

    Existing environment variables are never overwritten. The file is read
    only once unless force is True.

    Args:
        force (bool): Read the file again even if it was already loaded.
    """
    global _loaded
    if _loaded and not force:
        return
    _loaded = True

    path = find_env_file()
    if path is None:
        return
    for key, value in parse_env_file(path).items():
        os.environ.setdefault(key, value)

# endregion

# ==========

# region Env Accessors

def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return a setting.

    Args:
        key (str): Name of the setting.
        default (str, optional): Value returned if the setting is missing or empty.

    Returns:
        str | None: Value of the setting, or the default.
    """
    load_env()
    value = os.environ.get(key)
    return value if value not in (None, "") else default


def require(key: str) -> str:
    """Return a setting that must exist.

    Args:
        key (str): Name of the setting.

    Returns:
        str: Value of the setting.

    Raises:
        RuntimeError: If the setting is missing or empty.
    """
    value = get(key)
    if value is None:
        raise RuntimeError(
            f"Missing required setting '{key}'. Copy .env.example to .env and fill it in, "
            f"or set the {ENV_PATH_VARIABLE} variable to the path of your .env file."
        )
    return value


def get_list(key: str, sep: str = ",") -> List[str]:
    """Return a setting split into a list.

    Args:
        key (str): Name of the setting.
        sep (str): Separator between the items.

    Returns:
        List[str]: Stripped non-empty items, or an empty list if the setting is missing.
    """
    raw = get(key)
    if raw is None:
        return []
    return [item.strip() for item in raw.split(sep) if item.strip()]


def get_dict(key: str, sep: str = ",", pair_sep: str = ":") -> Dict[str, str]:
    """Return a setting parsed as key/value pairs.

    Args:
        key (str): Name of the setting.
        sep (str): Separator between the pairs.
        pair_sep (str): Separator between a pair key and its value.

    Returns:
        Dict[str, str]: Parsed pairs, or an empty dict if the setting is missing.
    """
    result: Dict[str, str] = {}
    for item in get_list(key, sep):
        if pair_sep in item:
            name, value = item.split(pair_sep, 1)
            result[name.strip()] = value.strip()
    return result

# endregion
