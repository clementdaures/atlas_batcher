# -*- coding: utf-8 -*-
"""Tests for core/tractor.py

Covers the ALF job creation, the versioning of the existing renders, the
tractor-spool command line and the configuration validation. The background
thread and the subprocess are replaced by synchronous fakes.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import types

# pytest modules
import pytest

# atlas modules
from atlas_manager.plugins.batcher.core import tractor
from atlas_manager.plugins.batcher.core.tractor import RenderEntry

JOB = dict(job_title="job", project="Andhakara", priority=3, user="alice", step=5, renderer="Karma")

# endregion

# ==========

# region Fixtures

@pytest.fixture(autouse=True)
def sync_thread(monkeypatch):
    """Run the versioning thread synchronously."""
    class SyncThread:
        def __init__(self, target, args=(), daemon=None):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(tractor, "threading", types.SimpleNamespace(Thread=SyncThread))


@pytest.fixture
def usd(tmp_path):
    """Create a fake USD file."""
    path = tmp_path / "shots" / "scene.usda"
    path.parent.mkdir()
    path.write_text("", encoding="utf-8")
    return path


@pytest.fixture
def fake_spool(monkeypatch):
    """Replace subprocess in the tractor module.

    Returns:
        types.SimpleNamespace: Recorder with cmd, kwargs, lines, returncode and error.
    """
    state = types.SimpleNamespace(cmd=None, kwargs=None, lines=["job 123 spooled\n"], returncode=0, error=None)

    class FakeProcess:
        def __init__(self, cmd, **kwargs):
            if state.error:
                raise state.error
            state.cmd, state.kwargs = cmd, kwargs
            self.stdout = iter(state.lines)
            self.returncode = state.returncode

        def wait(self):
            return self.returncode

    monkeypatch.setattr(tractor, "subprocess", types.SimpleNamespace(Popen=FakeProcess, PIPE=-1, STDOUT=-2))
    return state


def _task_lines(alf_path):
    return [line for line in alf_path.read_text(encoding="utf-8").splitlines() if line.startswith(" Task")]

# endregion

# ==========

# region ALF Creation

def test_empty_render_list_creates_nothing(tmp_path):
    assert tractor.create_alf_from_render_list({}, render_dir=tmp_path, **JOB) is None


def test_alf_header_and_footer(tmp_path, usd):
    alf = tractor.create_alf_from_render_list({"s": [RenderEntry(usd, 1001, 1010, 1)]}, render_dir=tmp_path, **JOB)
    assert alf == (tmp_path / "job.alf").resolve()
    lines = alf.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("Job -title {job} -projects {Andhakara} -priority {3} -owner {alice}")
    assert lines[0].endswith("-subtasks {")
    assert "-maxactive" not in lines[0]
    assert lines[-1] == "}"


def test_alf_max_blades_adds_maxactive(tmp_path, usd):
    alf = tractor.create_alf_from_render_list(
        {"s": [RenderEntry(usd, 1001, 1010, 1)]}, render_dir=tmp_path, max_blades=4, **JOB
    )
    assert "-maxactive {4}" in alf.read_text(encoding="utf-8").splitlines()[0]


def test_alf_creates_one_task_per_batch_of_frames(tmp_path, usd):
    alf = tractor.create_alf_from_render_list({"s": [RenderEntry(usd, 1001, 1010, 1)]}, render_dir=tmp_path, **JOB)
    tasks = _task_lines(alf)
    assert len(tasks) == 2
    assert "{job_Task_1_2}" in tasks[0] and "{job_Task_2_2}" in tasks[1]
    assert "-f 1001 -n 5 -i 1" in tasks[0]
    assert "-f 1006 -n 5 -i 1" in tasks[1]


def test_alf_takes_the_increment_into_account(tmp_path, usd):
    alf = tractor.create_alf_from_render_list({"s": [RenderEntry(usd, 1001, 1010, 2)]}, render_dir=tmp_path, **JOB)
    tasks = _task_lines(alf)
    assert len(tasks) == 1  # frames 1001, 1003, 1005, 1007, 1009
    assert "-f 1001 -n 5 -i 2" in tasks[0]


def test_alf_numbers_the_tasks_across_entries(tmp_path, usd):
    entries = [RenderEntry(usd, 1001, 1005, 1), RenderEntry(usd, 1050, 1050, 1)]
    alf = tractor.create_alf_from_render_list({"s": entries}, render_dir=tmp_path, **JOB)
    tasks = _task_lines(alf)
    assert all(f"{{job_Task_{n}_2}}" in task for n, task in enumerate(tasks, start=1))


def test_alf_husk_command(tmp_path, usd):
    alf = tractor.create_alf_from_render_list({"s": [RenderEntry(usd, 1001, 1005, 1)]}, render_dir=tmp_path, **JOB)
    task = _task_lines(alf)[0]
    live_pattern = str(tmp_path / "live" / "scene" / "scene.%04d.exr").replace("\\", "/")
    assert '"C:/fake/bin/husk.exe"' in task  # backslashes of the setting are normalised
    assert "-R Karma" in task
    assert f'-o "{live_pattern}"' in task
    assert f'"{str(usd.resolve())}"' in task
    assert "-service {PixarRender}" in task


def test_alf_creates_the_live_and_edit_folders(tmp_path, usd):
    tractor.create_alf_from_render_list({"s": [RenderEntry(usd, 1001, 1005, 1)]}, render_dir=tmp_path, **JOB)
    assert (tmp_path / "live" / "scene").is_dir()
    assert (tmp_path / "edit").is_dir()

# endregion

# ==========

# region Render Versioning

def test_existing_live_renders_are_versioned_into_edit(tmp_path, usd):
    live = tmp_path / "live" / "scene"
    live.mkdir(parents=True)
    (live / "scene.1001.exr").write_text("a", encoding="utf-8")
    (live / "scene.1002.exr").write_text("b", encoding="utf-8")
    (live / "notes.txt").write_text("c", encoding="utf-8")

    entries = {"s": [RenderEntry(usd, 1001, 1002, 1)]}
    tractor.create_alf_from_render_list(entries, render_dir=tmp_path, **JOB)
    v001 = tmp_path / "edit" / "scene" / "v001"
    assert sorted(p.name for p in v001.iterdir()) == ["scene.1001.exr", "scene.1002.exr"]

    tractor.create_alf_from_render_list(entries, render_dir=tmp_path, **JOB)
    assert (tmp_path / "edit" / "scene" / "v002").is_dir()


def test_nothing_is_versioned_without_existing_frames(tmp_path, usd):
    tractor.create_alf_from_render_list({"s": [RenderEntry(usd, 1001, 1002, 1)]}, render_dir=tmp_path, **JOB)
    assert not (tmp_path / "edit" / "scene").exists()

# endregion

# ==========

# region Tractor Submission

def test_spool_builds_the_command_line(fake_spool, tmp_path):
    alf = tmp_path / "job.alf"
    code, output = tractor.spool_to_tractor(alf, "alice", "Andhakara", 3, [])
    assert (code, output) == (0, "job 123 spooled")
    assert fake_spool.cmd == (
        r'"C:\fake\bin\tractor-spool.bat" -A --projects=Andhakara --user=alice --priority=3 ' f'"{alf}"'
    )
    assert fake_spool.kwargs["shell"] is True


def test_spool_restricts_the_job_to_the_selected_blades(fake_spool, tmp_path):
    tractor.spool_to_tractor(tmp_path / "job.alf", "alice", "Andhakara", 3, ["blade-01", "blade-02"])
    assert ' "--service=blade-01 || blade-02" ' in fake_spool.cmd


def test_spool_returns_the_tool_return_code(fake_spool, tmp_path):
    fake_spool.returncode = 2
    fake_spool.lines = ["first\n", "second\n"]
    assert tractor.spool_to_tractor(tmp_path / "job.alf", "alice", "P", 1, []) == (2, "first\nsecond")


def test_spool_reports_an_error_instead_of_raising(fake_spool, tmp_path):
    fake_spool.error = OSError("no tractor-spool")
    code, output = tractor.spool_to_tractor(tmp_path / "job.alf", "alice", "P", 1, [])
    assert code == -1
    assert output == "Spooling error: no tractor-spool"


def test_spool_requires_the_executable_setting(empty_env, tmp_path):
    with pytest.raises(RuntimeError, match="TRACTOR_SPOOL_PATH"):
        tractor.spool_to_tractor(tmp_path / "job.alf", "alice", "P", 1, [])

# endregion

# ==========

# region Configuration Validation

def test_validate_accepts_a_complete_configuration(tmp_path):
    husk = tmp_path / "husk.exe"
    husk.write_text("", encoding="utf-8")
    assert tractor.validate_tractor_config(husk, "alice", "Andhakara") == (True, "")


def test_validate_rejects_a_missing_husk(tmp_path):
    ok, message = tractor.validate_tractor_config(tmp_path / "husk.exe", "alice", "Andhakara")
    assert not ok and "Husk executable not found" in message


@pytest.mark.parametrize("user, project, expected", [
    ("  ", "Andhakara", "Username is required"),
    ("alice", "", "Project name is required"),
])
def test_validate_rejects_empty_user_or_project(tmp_path, user, project, expected):
    husk = tmp_path / "husk.exe"
    husk.write_text("", encoding="utf-8")
    assert tractor.validate_tractor_config(husk, user, project) == (False, expected)

# endregion
