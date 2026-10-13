# -*- coding: utf-8 -*-
"""Tractor core functions

This module handles the ALF file creation and the Tractor job submission of
Atlas Batcher.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import subprocess
import threading
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass

# atlas modules
from atlas_manager.plugins.batcher.core import utils

# endregion

# ==========

# region Render Data

@dataclass
class RenderEntry:
    """Data structure of a render list entry.

    Attributes:
        path (Path): Path of the USD file to render.
        start (int): Start frame.
        end (int): End frame.
        inc (int): Frame increment.
    """

    path: Path
    start: int
    end: int
    inc: int

# endregion

# ==========

# region ALF Creation

def create_alf_from_render_list(
    render_list: Dict[str, List[RenderEntry]],
    job_title: str,
    project: str,
    priority: int,
    user: str,
    step: int,
    renderer: str,
    render_dir: Path,
    max_blades: int = 0,
) -> Path:

    """Create an ALF job file from the render list.

    One husk task is created per batch of `step` frames. The live/ and edit/
    subfolders of the render directory are created, and the renders already
    present in live/ are versioned into edit/ in a background thread.

    Args:
        render_list (Dict[str, List[RenderEntry]]): Render entries per shot key.
        job_title (str): Title of the Tractor job.
        project (str): Tractor project name.
        priority (int): Job priority.
        user (str): Job owner.
        step (int): Number of frames per task.
        renderer (str): Renderer plugin name passed to husk.
        render_dir (Path): Render output directory.
        max_blades (int): Maximum number of simultaneous blades, 0 for unlimited.

    Returns:
        Path | None: Path of the written .alf file, or None if the render list is empty.
    """
    if not render_list:
        return None

    husk_path = str(utils.husk_path()).replace("\\", "/")

    # live/ and edit/ subdirs
    live_dir = render_dir / "live"
    edit_dir = render_dir / "edit"
    live_dir.mkdir(parents=True, exist_ok=True)
    edit_dir.mkdir(parents=True, exist_ok=True)

    alf_lines = []
    max_active_str = f"-maxactive {{{max_blades}}}" if max_blades > 0 else ""

    alf_lines.append(
        f'Job -title {{{job_title}}} -projects {{{project}}} -priority {{{priority}}} -owner {{{user}}} {max_active_str} -subtasks {{'
    )

    task_count = 0
    total_tasks = sum(
        (len(range(entry.start, entry.end + 1, entry.inc)) + step - 1) // step
        for entries in render_list.values()
        for entry in entries
    )

    for shot_key, entries in render_list.items():
        for entry in entries:
            stem = entry.path.stem
            usd_path = str(entry.path.resolve()).replace("\\", "/")

            # Pro output: render_dir/pro/{stem}/{stem}.%04d.exr
            live_output_dir = live_dir / stem
            live_output_dir.mkdir(parents=True, exist_ok=True)
            output_pattern = str(live_output_dir / f"{stem}.%04d.exr").replace("\\", "/")

            frames = list(range(entry.start, entry.end + 1, entry.inc))
            frame_batches = [frames[i:i + step] for i in range(0, len(frames), step)]

            for batch in frame_batches:
                task_count += 1
                start_frame = batch[0]
                n_frames = len(batch)
                task_title = f"{job_title}_Task_{task_count}_{total_tasks}"

                husk_cmd = (
                    f'"{husk_path}" '
                    f'-s /Render/rendersettings --make-output-path '
                    f'-f {start_frame} -n {n_frames} -i {entry.inc} '
                    f'-R {renderer} '
                    f'--purpose geometry,render '
                    f'--complexity veryhigh '
                    f'--windows-console wait '
                    f'-o "{output_pattern}" '
                    f'"{usd_path}"'
                )

                alf_lines.append(
                    f' Task -title {{{task_title}}} -cmds {{ RemoteCmd {{ {husk_cmd} }} -service {{PixarRender}} }}'
                )

    alf_lines.append('}')

    alf_path = (render_dir / f"{job_title}.alf").resolve()
    alf_path.parent.mkdir(parents=True, exist_ok=True)

    with open(alf_path, "w", encoding="utf-8") as f:
        f.write("\n".join(alf_lines))

    # --- Version live renders into edit ---
    threading.Thread(
        target=_version_renders_to_edit,
        args=(render_list, live_dir, edit_dir),
        daemon=True
    ).start()

    return alf_path


def _version_renders_to_edit(
    render_list: Dict[str, List[RenderEntry]],
    live_dir: Path,
    edit_dir: Path,
) -> None:
    """Copy the existing renders from live/{stem}/ into edit/{stem}/v00X/.

    Frames are only copied if they already exist in live (i.e. a previous submission).

    Args:
        render_list (Dict[str, List[RenderEntry]]): Render entries per shot key.
        live_dir (Path): Folder containing the live renders.
        edit_dir (Path): Folder containing the versioned renders.
    """
    import shutil

    for entries in render_list.values():
        for entry in entries:
            stem = entry.path.stem
            live_stem_dir = live_dir / stem

            if not live_stem_dir.exists():
                continue

            existing_frames = list(live_stem_dir.glob("*.exr"))
            if not existing_frames:
                continue

            # Get next version folder
            version_path = utils.get_next_render_version(edit_dir, stem)
            version_path.mkdir(parents=True, exist_ok=True)

            for frame in existing_frames:
                shutil.copy2(frame, version_path / frame.name)

            print(f"Versioned {len(existing_frames)} frames: {stem} → {version_path}")

# endregion

# ==========

# region Tractor Submission

def spool_to_tractor(alf_path: Path, user: str, project: str, priority: int, crews: list[str]) -> tuple[int, str]:
    """Spool an ALF file to Tractor with tractor-spool.

    The command is executed with shell=True to correctly handle paths with
    spaces and || separators.

    Args:
        alf_path (Path): Path of the ALF file.
        user (str): Job owner.
        project (str): Tractor project name.
        priority (int): Job priority.
        crews (list[str]): Blade names the job is restricted to, empty for no restriction.

    Returns:
        tuple[int, str]: Return code of tractor-spool (-1 on error) and its output.
    """
    tractor_spool = utils.tractor_spool_path()
    service_str = " || ".join(crews) if crews else ""

    cmd_str = (
        f'"{tractor_spool}" -A'
        f' --projects={project}'
        f' --user={user}'
        f' --priority={priority}'
        + (f' "--service={service_str}"' if service_str else "")
        + f' "{str(alf_path)}"'
    )

    try:
        proc = subprocess.Popen(
            cmd_str,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
        )
        output_lines = []
        assert proc.stdout is not None
        for line in proc.stdout:
            output_lines.append(line.rstrip())
        proc.wait()
        return proc.returncode, "\n".join(output_lines)

    except Exception as e:
        return -1, f"Spooling error: {str(e)}"


def validate_tractor_config(husk_path: Path, user: str, project: str) -> tuple[bool, str]:
    """Validate the Tractor configuration before the submission.

    Args:
        husk_path (Path): Path of the husk executable.
        user (str): Username.
        project (str): Project name.

    Returns:
        tuple[bool, str]: Validity flag and an error message (empty if valid).
    """
    if not husk_path.exists():
        return False, f"Husk executable not found: {husk_path}"

    if not user.strip():
        return False, "Username is required"

    if not project.strip():
        return False, "Project name is required"

    return True, ""

# endregion
