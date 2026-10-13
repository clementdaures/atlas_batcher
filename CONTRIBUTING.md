# Contributing to Atlas Batcher

Thanks for helping out. This is the render batching tool for the
*Andhakara* short, so changes should stay safe for artists mid-shot and
for the render farm; see below for what that means in practice.

## Before you start

Read the **Project Layout** section of [`README.md`](README.md). The one
rule that matters most: **`core` never imports from `ui`**. If a change
would require `core` to import PySide6 or a `ui` module, it belongs in
`ui` instead, calling into `core` for the render / Tractor part.

## Private settings

Never hardcode a Tractor host or credential, a server or install path, or
an artist machine name in the source code.

- Add the value to `.env` and a placeholder to `.env.example`, then read
  it with `env.require("KEY")`, `env.get("KEY", default)`, `env.get_list`
  or `env.get_dict` from `core/env.py`.
- Read settings inside the function that needs them rather than at import
  time, so that a missing key gives a clear error instead of breaking the
  import of the module.
- Never commit `.env` (it is listed in `.gitignore`), and never paste real
  values in code, docstrings, issues or PRs.

## Branches & commits

- Branch from `main`: `feat/<short-name>`, `fix/<short-name>`,
  `docs/<short-name>`, `chore/<short-name>`.
- Commit messages: `type(scope): summary`, e.g.
  `fix(core.tractor): quote the spool path when it contains spaces`.
  Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`.
- Keep commits focused — a rename/move and a behavior change belong in
  separate commits so the diff is reviewable.

## Where new code goes

- Render list and local rendering (husk) → `core/render.py`.
- ALF creation and Tractor spooling → `core/tractor.py`.
- Tractor farm scanning (blades, RAM, ping) → `core/tractor_scan.py`.
- Paths, artist name, shot / asset / USD discovery → `core/utils.py`.
- Private settings access → `core/env.py` (values go in `.env`).
- A new window/dialog → `ui/dialog/`.
- The main window behaviour → `ui/main.py`.
- Icons and graphic assets → `ui/icon/`.

## Code style

- Every module starts with `# -*- coding: utf-8 -*-` and a docstring
  with a title, a short description and the `Author` / `Website` /
  `Created` block.
- Use Google-style docstrings (`Args:`, `Returns:`, `Raises:`) on every
  public class, function and method.
- Organise each module in `# region` / `# endregion` blocks separated by
  a `# ==========` line, starting with `# region Imports & Config`
  (imports grouped as python, pyside, dcc, atlas modules).
- Keep the existing line endings of a file (the sources use CRLF) so the
  diff only shows real changes.

## Before opening a PR

```bash
ruff check .
black .
pytest
```

- Add or update a test in `tests/` for any `core` change (mock the
  Tractor server and `subprocess` instead of calling them).
- Update `README.md` if you moved, renamed, or added a module or a `.env`
  key — the project layout and the configuration table are the map new
  contributors use, and a stale map is worse than none.
- Keep the PR description focused on *why*, not just *what* — the diff
  already shows what changed.

## Reporting bugs / requesting features

Open an issue describing the problem or the feature. For anything that
could affect a job already on the farm (e.g. a change to the ALF
content, the `live/` and `edit/` render folders, or the render output
paths), please flag that explicitly in the issue or PR so it can get
extra review.

## Code of conduct

Be respectful and assume good faith — this is a small student/indie
production team, not a large open-source project, and most contributors
are also credited crew on the film.
