# -*- coding: utf-8 -*-
"""Render core functions

This module handles the render list management and the local rendering
operations (husk) of Atlas Batcher.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass

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
    inc: int = 1

# endregion

# ==========

# region Render Manager

class RenderManager:
    """Manage the render list and the local rendering operations.

    Args:
        husk_path (Path): Path of the husk executable.
        renderer (str): Renderer plugin name, e.g. 'Karma'.

    Example:
        manager = RenderManager(husk_path=Path("husk.exe"), renderer="Karma")
        manager.add_to_render_list("SHOT", [Path("shot.usda")], 1001, 1100)
        manager.render_all(Path("renders"))
    """

    def __init__(self, husk_path: Path, renderer: str):
        """Initialize the manager with an empty render list."""
        self.husk_path = husk_path
        self.renderer = renderer
        self.render_list: Dict[str, List[RenderEntry]] = {}
        self.cancel_render = False
        self.current_process: Optional[subprocess.Popen] = None

    def add_to_render_list(
            self,
            shot_key: str,
            usd_paths: List[Path],
            start_frame: int,
            end_frame: int,
            inc_frame: int = 1,
    ) -> Tuple[int, int, int]:
        """Add files to the render list.

        A file is skipped when its range is already covered by an existing entry,
        and merged with the existing entry when the ranges overlap.

        Args:
            shot_key (str): Key identifying the shot, e.g. "SEQUENCE: sq010 / SHOT: sh0010".
            usd_paths (List[Path]): USD file paths to add.
            start_frame (int): Start frame.
            end_frame (int): End frame.
            inc_frame (int): Frame increment.

        Returns:
            Tuple[int, int, int]: Number of new, merged and skipped entries.
        """
        new_entries = merged_entries = skipped_entries = 0

        for usd_path in usd_paths:
            if shot_key not in self.render_list:
                self.render_list[shot_key] = []

            existing_list = self.render_list[shot_key]
            fname = usd_path.name

            merged = skipped = False

            # Check for overlapping or duplicate entries
            for existing in existing_list:
                if existing.path.name != fname:
                    continue

                ex_start = existing.start
                ex_end = existing.end

                # Check if new range is completely within existing
                if start_frame >= ex_start and end_frame <= ex_end:
                    existing.inc = inc_frame
                    skipped_entries += 1
                    skipped = True
                    break

                # Check if ranges overlap and can be merged
                if not (end_frame < ex_start or start_frame > ex_end):
                    existing.inc = inc_frame
                    existing.start = min(start_frame, ex_start)
                    existing.end = max(end_frame, ex_end)
                    merged_entries += 1
                    merged = True
                    break

            # Add new entry if not merged or skipped
            if not merged and not skipped:
                existing_list.append(
                    RenderEntry(path=usd_path, start=start_frame, end=end_frame, inc=inc_frame)
                )
                new_entries += 1

        return new_entries, merged_entries, skipped_entries

    def add_fml_to_render_list(
            self,
            shot_key: str,
            usd_paths: List[Path],
            start_frame: int,
            end_frame: int,
            inc_frame: int = 1,
            custom_mid_frame: Optional[int] = None
    ) -> Tuple[int, int, int, Optional[str]]:
        """Add the first, middle and last frames to the render list.

        Args:
            shot_key (str): Key identifying the shot.
            usd_paths (List[Path]): USD file paths to add.
            start_frame (int): Start frame.
            end_frame (int): End frame.
            inc_frame (int): Frame increment.
            custom_mid_frame (int, optional): Custom middle frame. The average of the
                start and end frames is used if None.

        Returns:
            Tuple[int, int, int, Optional[str]]: Number of new, merged and skipped
                entries, and an error message (None if the middle frame is valid).
        """
        # Calculate middle frame
        if custom_mid_frame is not None:
            if custom_mid_frame < start_frame or custom_mid_frame > end_frame:
                return 0, 0, 0, f"Middle frame {custom_mid_frame} is outside range [{start_frame}-{end_frame}]"
            mid = custom_mid_frame
        else:
            mid = (start_frame + end_frame) // 2

        # Create three frame ranges
        frame_ranges = [
            (start_frame, start_frame),  # Start frame
            (mid, mid),  # Middle frame
            (end_frame, end_frame)  # End frame
        ]

        new_entries = merged_entries = skipped_entries = 0

        for usd_path in usd_paths:
            if shot_key not in self.render_list:
                self.render_list[shot_key] = []

            existing_list = self.render_list[shot_key]
            fname = usd_path.name

            # Process each frame range
            for frame_start, frame_end in frame_ranges:
                merged = skipped = False

                for existing in existing_list:
                    if existing.path.name != fname:
                        continue

                    ex_start = existing.start
                    ex_end = existing.end

                    # Check if within existing range
                    if frame_start >= ex_start and frame_end <= ex_end:
                        existing.inc = inc_frame
                        skipped_entries += 1
                        skipped = True
                        break

                    # Check if can be merged
                    if not (frame_end < ex_start or frame_start > ex_end):
                        existing.inc = inc_frame
                        existing.start = min(frame_start, ex_start)
                        existing.end = max(frame_end, ex_end)
                        merged_entries += 1
                        merged = True
                        break

                # Add new entry
                if not merged and not skipped:
                    existing_list.append(
                        RenderEntry(path=usd_path, start=frame_start, end=frame_end, inc=inc_frame)
                    )
                    new_entries += 1

        return new_entries, merged_entries, skipped_entries, None

    def remove_from_render_list(
            self,
            shot_key: str,
            filename: str,
            frame_range: str
    ) -> bool:
        """Remove a specific entry from the render list.

        Args:
            shot_key (str): Shot identifier.
            filename (str): USD file name.
            frame_range (str): Frame range string, e.g. "1001-1100".

        Returns:
            bool: True if the entry was removed, False otherwise.
        """
        if shot_key not in self.render_list:
            return False

        for entry in list(self.render_list[shot_key]):
            if (entry.path.name == filename and
                    f"{entry.start}-{entry.end}" == frame_range):
                self.render_list[shot_key].remove(entry)

                # Clean up empty shot keys
                if not self.render_list[shot_key]:
                    del self.render_list[shot_key]

                return True

        return False

    def clear_render_list(self) -> None:
        """Clear all the entries of the render list."""
        self.render_list.clear()

    def get_render_list_sorted(self) -> Dict[str, List[RenderEntry]]:
        """Get the render list with its entries sorted by file name and start frame.

        Returns:
            Dict[str, List[RenderEntry]]: Sorted render entries per shot key.
        """
        sorted_list = {}
        for shot_key, entries in self.render_list.items():
            sorted_list[shot_key] = sorted(
                entries,
                key=lambda e: (e.path.name.lower(), e.start)
            )
        return sorted_list

    def render_all(
            self,
            render_output_dir: Path,
            progress_callback: Optional[Callable[[int, int], None]] = None,
            log_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str]:
        """Render all the entries of the render list with husk.

        Args:
            render_output_dir (Path): Directory for the render output.
            progress_callback (Callable[[int, int], None], optional): Called with
                (current, total) before each entry is rendered.
            log_callback (Callable[[str], None], optional): Called with each log message.

        Returns:
            Tuple[bool, str]: Success flag and a message.
        """
        self.cancel_render = False

        # Collect all entries
        all_entries = [
            (shot_key, entry)
            for shot_key, entries in self.render_list.items()
            for entry in entries
        ]

        if not all_entries:
            return False, "Render list is empty"

        total = len(all_entries)

        if log_callback:
            log_callback(f"Starting render: {total} entries\n")

        for idx, (shot_key, entry) in enumerate(all_entries, start=1):
            if self.cancel_render:
                if log_callback:
                    log_callback("Render cancelled by user\n")
                return False, "Render cancelled"

            # Update progress
            if progress_callback:
                progress_callback(idx, total)

            # Build command
            usd_path = entry.path
            start_frame = entry.start
            end_frame = entry.end
            base_name = usd_path.stem
            output_pattern = str(render_output_dir / f"{base_name}.%04d.exr")

            cmd = [
                str(self.husk_path),
                "--renderer", self.renderer,
                "-f", str(start_frame),
                "-n", str(end_frame - start_frame + 1),
                "--frame-inc", str(entry.inc),
                "-o", output_pattern,
                str(usd_path)
            ]

            if log_callback:
                log_callback(f"\n🔹 Rendering {base_name} ({shot_key})\n")
                log_callback(f"   Frames: {start_frame}-{end_frame}\n")
                log_callback(f"   Output: {output_pattern}\n")

            # Execute render
            try:
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE

                self.current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    startupinfo=startupinfo
                )

                # Stream output
                assert self.current_process.stdout is not None
                for line in self.current_process.stdout:
                    if log_callback:
                        log_callback(line)

                    if self.cancel_render:
                        try:
                            self.current_process.terminate()
                        except Exception:
                            pass
                        return False, "Render cancelled"

                self.current_process.wait()

                if self.current_process.returncode != 0:
                    return False, f"Render failed with code {self.current_process.returncode}"

                if log_callback:
                    log_callback(f"✓ {base_name} [{start_frame}-{end_frame}] completed\n")

            except Exception as e:
                error_msg = f"Render failed for {base_name}: {repr(e)}"
                if log_callback:
                    log_callback(error_msg + "\n")
                return False, error_msg

        return True, "All renders completed successfully"

    def cancel_current_render(self) -> None:
        """Cancel the currently running render."""
        self.cancel_render = True
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
            except Exception:
                pass

# endregion

# ==========

# region Frame Helpers

def calculate_mid_frame(start: int, end: int, custom: Optional[int] = None) -> int:
    """Calculate the middle frame.

    Args:
        start (int): Start frame.
        end (int): End frame.
        custom (int, optional): Custom middle frame, returned as is if given.

    Returns:
        int: Middle frame number.
    """
    if custom is not None:
        return custom
    return (start + end) // 2


def validate_mid_frame(mid: int, start: int, end: int) -> bool:
    """Validate that the middle frame is within the frame range.

    Args:
        mid (int): Middle frame.
        start (int): Start frame.
        end (int): End frame.

    Returns:
        bool: True if the middle frame is within the range, False otherwise.
    """
    return start <= mid <= end

# endregion
