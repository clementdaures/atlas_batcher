# -*- coding: utf-8 -*-
"""Utility functions to resolve Atlas Batcher information

Resolves the artist name, the storage paths and the executables, and discovers
the sequences, shots, assets and USD files to render. The private values
(storage roots, install paths, artist machine map) are read from the .env file
through the env module.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import platform
import os
import re
from pathlib import Path
from typing import Tuple, List, Optional

# atlas modules
from atlas_manager.plugins.batcher.core import env

# endregion

# ==========

# region User Helpers

def _user_dict():
    """Return the machine name to artist name mapping.

    Returns:
        dict[str, str]: Mapping read from ATLAS_USER_MAP, e.g. {'MACHINE01': 'username'}.
    """
    return env.get_dict("ATLAS_USER_MAP")

def user():
    """Return the artist name of the current machine.

    Returns:
        str: Artist name, or 'unknown' if the machine is not in the mapping.
    """
    machine = platform.node()
    users = _user_dict()
    return users.get(machine, "unknown")

# endregion

# ==========

# region Path Helpers

def shotpath():
    """Return the root folder of the shots.

    Returns:
        str: Value of ATLAS_SHOT_ROOT.
    """
    return env.require("ATLAS_SHOT_ROOT")

def relative_usd_path():
    """Return the USD folder of a shot, relative to the shot folder.

    Returns:
        str: Relative path 'rdr/houdini/live' (with Windows separators).
    """
    return r"rdr\houdini\live"

def relative_render_path():
    """Return the render folder of a shot, relative to the shot folder.

    Returns:
        str: Relative path 'rdr/houdini/render' (with Windows separators).
    """
    return r"rdr\houdini\render"

def husk_path():
    """Return the path of the husk executable.

    Returns:
        str: Value of HUSK_PATH.
    """
    return env.require("HUSK_PATH")

def hython_path():
    """Return the path of the hython executable.

    Returns:
        str: Value of HYTHON_PATH.
    """
    return env.require("HYTHON_PATH")

def tractor_spool_path() -> str:
    """Return the full path of the tractor-spool executable.

    Returns:
        str: Value of TRACTOR_SPOOL_PATH.
    """
    return env.require("TRACTOR_SPOOL_PATH")

def renderer_variable():
    """Return the Hydra renderer plugin name passed to husk.

    Returns:
        str: Renderer plugin name.
    """
    return "HdPrmanLoaderRendererPlugin"

# endregion

# ==========

# region Render Versioning

def get_next_render_version(edit_dir: Path, stem: str) -> Path:
    """Get the next available versioned folder for a given stem.

    For example edit/my_scene/v001/, then edit/my_scene/v002/.

    Args:
        edit_dir (Path): Folder containing the versioned render folders.
        stem (str): Name of the USD file without extension.

    Returns:
        Path: First version folder that does not exist yet.
    """
    version = 1
    while True:
        version_path = edit_dir / stem / f"v{version:03d}"
        if not version_path.exists():
            return version_path
        version += 1

# endregion

# ==========

# region Shot Discovery

def sequences():
    """List the sequences found in the shot root.

    Returns:
        tuple[list[str], list[str]]: The names of the entries of the shot root, and
            the full paths of the entries that are folders.
    """
    sequence_path_list = []
    default_path = shotpath()
    sequence_list = os.listdir(default_path)
    for seq in sequence_list:
        if os.path.isdir(os.path.join(default_path, seq)):
            sequence_path_list.append(os.path.join(default_path, seq))

    return sequence_list, sequence_path_list

def shots(sequence_path: str):
    """List the shots of a sequence.

    Only the folders whose name ends with 'sh' followed by digits are kept.

    Args:
        sequence_path (str): Full path of the sequence folder.

    Returns:
        tuple[list[str], list[str]]: Shot names like ['sh001', 'sh002'] and the
            full paths of those shots. Both lists are empty if the sequence folder
            does not exist.
    """

    if not os.path.isdir(sequence_path):
        return [], []

    shot_number_list = []
    shot_path_list = []

    for entry in os.listdir(sequence_path):
        shot_full_path = os.path.join(sequence_path, entry)

        if not os.path.isdir(shot_full_path):
            continue

        match = re.search(r"(sh\d+)$", entry.lower())
        if not match:
            continue

        shot_number = match.group(1)

        shot_number_list.append(shot_number)
        shot_path_list.append(shot_full_path)

    return shot_number_list, shot_path_list

def solve_path(sequence_name, shot_name):
    """Resolve the folder of a shot.

    Args:
        sequence_name (str): Sequence folder name, e.g. 'SEQ_010'.
        shot_name (str): Shot name, e.g. 'sh020'.

    Returns:
        str: Path <shot root>/<sequence>/<seqXXXshYYY>, where the shot folder name
            has its underscores removed and is lower case.
    """
    default_path = shotpath()
    full_shot_name = sequence_name + shot_name
    full_shot_name = re.sub(r"_", "", full_shot_name)
    return os.path.join(default_path, sequence_name, full_shot_name.lower())

def usd_path(sequence_name, shot_name):
    """List the USD files of a shot.

    Args:
        sequence_name (str): Sequence folder name, e.g. 'SEQ_010'.
        shot_name (str): Shot name, e.g. 'sh020'.

    Returns:
        tuple[list[str], list[str]]: Names and full paths of the .usd and .usda
            files found in the USD folder of the shot.

    Raises:
        FileNotFoundError: If the USD folder of the shot does not exist.
    """
    relative_path = relative_usd_path()
    shot_path = solve_path(sequence_name, shot_name)
    absolute_path = os.path.join(shot_path, relative_path)

    usd_file = os.listdir(absolute_path)
    usd_list = []
    usd_path_list = []

    for usd in usd_file:
        if usd.endswith(".usd") or usd.endswith(".usda"):
            usd_list.append(usd)

            usd_path = os.path.join(absolute_path, usd)
            usd_path_list.append(usd_path)

    return usd_list, usd_path_list

def render_path(sequence_name, shot_name):
    """Return the render folder of a shot, creating it if needed.

    Args:
        sequence_name (str): Sequence folder name, e.g. 'SEQ_010'.
        shot_name (str): Shot name, e.g. 'sh020'.

    Returns:
        str: Path of the render folder of the shot.
    """
    relative_path = relative_render_path()
    shot_path = solve_path(sequence_name, shot_name)
    absolute_path = os.path.join(shot_path, relative_path)
    os.makedirs(absolute_path, exist_ok=True)

    return absolute_path

# endregion

# ==========

# region Asset Discovery

def assets(asset_type: str) -> Optional[Tuple[List[str], List[Path]]]:
    """List all the assets of a given type that contain a 'rdr' folder.

    The asset type folder (00_CHR, 01_PROP or 02_SET) is searched recursively for
    folders containing a 'rdr' subdirectory. The parent folder of 'rdr' is
    considered the asset folder, and its name is returned as the asset name.

    Args:
        asset_type (str): Type of asset to search for, one of:
            "Chara" (00_CHR), "Prop" (01_PROP) or "Set" (02_SET).

    Returns:
        tuple[list[str], list[Path]] | None: The asset names (parent of 'rdr') and
            the paths of the asset folders, sorted alphabetically. None if the
            base path does not exist or no assets are found.

    Example:
        asset_names, asset_paths = assets("Chara")
        print(asset_names)  # ['hero_character', 'villain_character', 'sidekick']
        print(asset_paths[0])  # <ATLAS_ASSET_ROOT>/00_CHR/hero_character
    """
    # Base asset path
    base_asset_path = Path(env.require("ATLAS_ASSET_ROOT"))

    # Map asset type to folder
    asset_folder_map = {
        "Chara": "00_CHR",
        "Prop": "01_PROP",
        "Set": "02_SET"
    }

    # Get the appropriate folder
    folder_name = asset_folder_map.get(asset_type)
    if not folder_name:
        print(f"Invalid asset type: {asset_type}")
        return None

    asset_type_path = base_asset_path / folder_name

    # Check if path exists
    if not asset_type_path.exists():
        print(f"Asset type path does not exist: {asset_type_path}")
        return None

    # Find all folders containing 'rdr'
    asset_names = []
    asset_paths = []

    try:
        # Search recursively for 'rdr' folders
        for rdr_folder in asset_type_path.rglob("rdr"):
            if rdr_folder.is_dir():
                # Get the parent folder (the actual asset folder)
                asset_folder = rdr_folder.parent
                asset_name = asset_folder.name

                # Avoid duplicates (in case there are multiple rdr folders in the same asset)
                if asset_name not in asset_names:
                    asset_names.append(asset_name)
                    asset_paths.append(asset_folder)

        # Sort alphabetically for consistent ordering
        if asset_names:
            sorted_pairs = sorted(zip(asset_names, asset_paths), key=lambda x: x[0].lower())
            asset_names, asset_paths = zip(*sorted_pairs)
            asset_names = list(asset_names)
            asset_paths = list(asset_paths)

            return asset_names, asset_paths
        else:
            print(f"No assets with 'rdr' folder found in {asset_type_path}")
            return None

    except Exception as e:
        print(f"Error searching for assets: {e}")
        return None


def usd_path_lookdev(asset_path: Path) -> Optional[Tuple[List[str], List[Path]]]:
    """List all the USD files within the rdr (lookdev) folder of an asset.

    Args:
        asset_path (Path): Path of the asset folder (parent of 'rdr').

    Returns:
        tuple[list[str], list[Path]] | None: The USD file names and their paths,
            sorted by name. None if the folder does not exist or no USD files
            are found.

    Example:
        usd_names, usd_paths = usd_path_lookdev(Path('<ATLAS_ASSET_ROOT>/00_CHR/rani'))
        print(usd_names)  # ['rani_lookdev_v001.usd', 'rani_lookdev_v002.usd']
    """
    rdr_path = asset_path / "rdr" / "houdini" / "live"

    if not rdr_path.exists():
        print(f"rdr folder not found in {asset_path}")
        return None

    # Find all USD files in the rdr folder and its subdirectories
    usd_files = []

    try:
        # Search for .usd and .usda files
        for pattern in ["*.usd", "*.usda", "*.usdc"]:
            usd_files.extend(rdr_path.rglob(pattern))

        if not usd_files:
            print(f"No USD files found in {rdr_path}")
            return None

        # Sort files
        usd_files.sort(key=lambda x: x.name.lower())

        # Extract names and paths
        usd_names = [f.name for f in usd_files]
        usd_paths = usd_files

        return usd_names, usd_paths

    except Exception as e:
        print(f"Error searching for USD files: {e}")
        return None

# endregion
