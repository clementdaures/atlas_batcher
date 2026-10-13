# -*- coding: utf-8 -*-
"""Tests for core/render.py

Covers the render list management (new, merged and skipped entries), the
first / middle / last frame helper, and the local husk rendering with a mocked
subprocess.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
from pathlib import Path

# pytest modules
import pytest

# atlas modules
from atlas_manager.plugins.batcher.core import render
from atlas_manager.plugins.batcher.core.render import RenderManager

SHOT = "SEQUENCE: sq010 / SHOT: sh0010"

# endregion

# ==========

# region Fixtures

@pytest.fixture
def manager():
    """Return a render manager with a fake husk executable."""
    return RenderManager(husk_path=Path("husk.exe"), renderer="Karma")


@pytest.fixture
def fake_popen(monkeypatch):
    """Replace subprocess.Popen in the render module.

    Returns:
        type: Recorder exposing calls, lines, returncode and terminated.
    """
    class Recorder:
        calls = []
        lines = ["frame 1\n"]
        returncode = 0
        terminated = False
        error = None

    class FakeProcess:
        def __init__(self, cmd, **kwargs):
            if Recorder.error:
                raise Recorder.error
            Recorder.calls.append(cmd)
            self.stdout = iter(Recorder.lines)
            self.returncode = Recorder.returncode

        def wait(self):
            return self.returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            Recorder.terminated = True

    Recorder.calls = []
    Recorder.lines = ["frame 1\n"]
    Recorder.returncode = 0
    Recorder.terminated = False
    Recorder.error = None
    monkeypatch.setattr(render.subprocess, "Popen", FakeProcess)
    return Recorder

# endregion

# ==========

# region Frame Helpers

def test_calculate_mid_frame_averages_the_range():
    assert render.calculate_mid_frame(1001, 1100) == 1050
    assert render.calculate_mid_frame(1, 10) == 5


def test_calculate_mid_frame_prefers_the_custom_frame():
    assert render.calculate_mid_frame(1001, 1100, custom=1020) == 1020


def test_validate_mid_frame_bounds_are_inclusive():
    assert render.validate_mid_frame(1001, 1001, 1100)
    assert render.validate_mid_frame(1100, 1001, 1100)
    assert not render.validate_mid_frame(1000, 1001, 1100)
    assert not render.validate_mid_frame(1101, 1001, 1100)

# endregion

# ==========

# region Render List

def test_add_creates_new_entries(manager):
    paths = [Path("a.usda"), Path("b.usda")]
    assert manager.add_to_render_list(SHOT, paths, 1001, 1100) == (2, 0, 0)
    entries = manager.render_list[SHOT]
    assert [(e.path.name, e.start, e.end, e.inc) for e in entries] == [
        ("a.usda", 1001, 1100, 1),
        ("b.usda", 1001, 1100, 1),
    ]


def test_add_skips_a_range_already_covered(manager):
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1100)
    assert manager.add_to_render_list(SHOT, [Path("a.usda")], 1010, 1020, 2) == (0, 0, 1)
    entry = manager.render_list[SHOT][0]
    assert (entry.start, entry.end) == (1001, 1100)
    assert entry.inc == 2  # the increment of the latest request wins


def test_add_merges_overlapping_ranges(manager):
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1050)
    assert manager.add_to_render_list(SHOT, [Path("a.usda")], 1040, 1100) == (0, 1, 0)
    entry = manager.render_list[SHOT][0]
    assert (entry.start, entry.end) == (1001, 1100)


def test_add_keeps_disjoint_ranges_separate(manager):
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1010)
    assert manager.add_to_render_list(SHOT, [Path("a.usda")], 1050, 1060) == (1, 0, 0)
    assert len(manager.render_list[SHOT]) == 2


def test_same_file_name_in_another_shot_is_independent(manager):
    manager.add_to_render_list("shot A", [Path("a.usda")], 1001, 1100)
    assert manager.add_to_render_list("shot B", [Path("a.usda")], 1001, 1100) == (1, 0, 0)


def test_add_fml_adds_first_middle_and_last_frames(manager):
    result = manager.add_fml_to_render_list(SHOT, [Path("a.usda")], 1001, 1101)
    assert result == (3, 0, 0, None)
    assert [(e.start, e.end) for e in manager.render_list[SHOT]] == [(1001, 1001), (1051, 1051), (1101, 1101)]


def test_add_fml_uses_the_custom_middle_frame(manager):
    manager.add_fml_to_render_list(SHOT, [Path("a.usda")], 1001, 1100, custom_mid_frame=1020)
    assert [e.start for e in manager.render_list[SHOT]] == [1001, 1020, 1100]


def test_add_fml_rejects_a_middle_frame_outside_the_range(manager):
    new, merged, skipped, error = manager.add_fml_to_render_list(
        SHOT, [Path("a.usda")], 1001, 1100, custom_mid_frame=2000
    )
    assert (new, merged, skipped) == (0, 0, 0)
    assert "2000" in error and "outside range" in error
    assert SHOT not in manager.render_list


def test_add_fml_skips_frames_already_in_the_list(manager):
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1100)
    assert manager.add_fml_to_render_list(SHOT, [Path("a.usda")], 1001, 1100) == (0, 0, 3, None)


def test_remove_deletes_the_matching_entry_and_empty_shots(manager):
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1100)
    assert not manager.remove_from_render_list(SHOT, "a.usda", "1-2")
    assert not manager.remove_from_render_list("unknown", "a.usda", "1001-1100")
    assert manager.remove_from_render_list(SHOT, "a.usda", "1001-1100")
    assert SHOT not in manager.render_list


def test_clear_empties_the_list(manager):
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1100)
    manager.clear_render_list()
    assert manager.render_list == {}


def test_sorted_list_orders_by_name_then_start_frame(manager):
    manager.add_to_render_list(SHOT, [Path("b.usda")], 1050, 1060)
    manager.add_to_render_list(SHOT, [Path("b.usda")], 1001, 1010)
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1100)
    ordered = manager.get_render_list_sorted()[SHOT]
    assert [(e.path.name, e.start) for e in ordered] == [("a.usda", 1001), ("b.usda", 1001), ("b.usda", 1050)]

# endregion

# ==========

# region Local Rendering

def test_render_all_with_an_empty_list(manager, tmp_path):
    assert manager.render_all(tmp_path) == (False, "Render list is empty")


def test_render_all_builds_the_husk_command(manager, tmp_path, fake_popen):
    usd = Path("shots") / "a.usda"
    manager.add_to_render_list(SHOT, [usd], 1001, 1010, 2)
    ok, message = manager.render_all(tmp_path)
    assert (ok, message) == (True, "All renders completed successfully")
    assert fake_popen.calls == [[
        "husk.exe", "--renderer", "Karma",
        "-f", "1001", "-n", "10", "--frame-inc", "2",
        "-o", str(tmp_path / "a.%04d.exr"), str(usd),
    ]]


def test_render_all_reports_progress_and_logs(manager, tmp_path, fake_popen):
    manager.add_to_render_list(SHOT, [Path("a.usda"), Path("b.usda")], 1001, 1010)
    progress, logs = [], []
    manager.render_all(tmp_path, progress_callback=lambda i, n: progress.append((i, n)), log_callback=logs.append)
    assert progress == [(1, 2), (2, 2)]
    assert logs[0] == "Starting render: 2 entries\n"
    assert "frame 1\n" in logs
    assert any("completed" in line for line in logs)


def test_render_all_stops_on_a_failing_process(manager, tmp_path, fake_popen):
    fake_popen.returncode = 3
    manager.add_to_render_list(SHOT, [Path("a.usda"), Path("b.usda")], 1001, 1010)
    assert manager.render_all(tmp_path) == (False, "Render failed with code 3")
    assert len(fake_popen.calls) == 1  # the second entry is not started


def test_render_all_reports_a_launch_error(manager, tmp_path, fake_popen):
    fake_popen.error = FileNotFoundError("husk.exe")
    manager.add_to_render_list(SHOT, [Path("a.usda")], 1001, 1010)
    ok, message = manager.render_all(tmp_path)
    assert not ok
    assert message.startswith("Render failed for a:")


def test_cancel_during_a_render_terminates_the_process(manager, tmp_path, fake_popen):
    manager.add_to_render_list(SHOT, [Path("a.usda"), Path("b.usda")], 1001, 1010)

    def log(text):
        if text == "frame 1\n":
            manager.cancel_current_render()

    assert manager.render_all(tmp_path, log_callback=log) == (False, "Render cancelled")
    assert fake_popen.terminated
    assert len(fake_popen.calls) == 1


def test_cancel_without_a_process_only_sets_the_flag(manager):
    manager.cancel_current_render()
    assert manager.cancel_render is True

# endregion
