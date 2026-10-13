# ATLAS BATCHER - ANDHAKARA
Pipeline repository for the animated short film Andhakara

## Version
1.00 — 12/10/26

## Designed For
SideFX Houdini 20.5 (husk / USD), Pixar Tractor 2.4, Python 3.11, PySide6

## Author
Clement Daures

- support@clementdaures.com (Pipeline TD / Dev / Rigging)

## Team
Léo Barachant (Animation 3D, Editing, Modeling)

Théo Berail (Storyboard, Scenario, Animation 3D)

Nino David (Modeling, Sculpting, Surfacing, Lighting)

Alicia Denux (Concept Art, Animation 3D)

Léa Genieys (Color Script, Lighting, Surfacing, Compositing)

Lilou Huet (Lighting, Modeling, Surfacing, Compositing)

Louna Perer (Grooming, CFX, Modeling, Surfacing)

Pablo Rodriguez (Scenario, Storyboard, FX, Layout)

Estelle Rupprecht (Concept Art, Cloth, CFX, Modeling)

Madelie Vaginay (Concept Art, Modeling, Surfacing, DMP)

## Logline
When her older sister accidentally dies in front of her, a stubborn teenager enters the world of the dead to bring back her soul.

## Repository Purpose
Atlas Batcher is a specialized PySide6 tool built to render USD files from the Andhakara pipeline, either locally or on the render farm. Integrated directly into the technical pipeline of Andhakara alongside Atlas Manager, it provides:

- USD file discovery for lookdev assets (characters, props, sets), shots, or any custom folder
- A render list with frame range management, including first / middle / last frame checks
- Local rendering with husk, with a progress bar and a live console
- Tractor submission: ALF job creation, blade selection by room, and spooling

## Tech Highlights
- **Render List Engine:** Entries are merged when their frame ranges overlap and skipped when already covered, so the same USD file is never rendered twice for the same frames.
- **Tractor Integration:** Builds the ALF job (one husk task per batch of frames), spools it with `tractor-spool`, and restricts it to the blades picked in the room filter. Blade states (idle, busy, nimby, unresponsive), physical RAM and ping are retrieved by the farm scanner.
- **Automatic Versioning:** Renders already present in `live/` are copied into `edit/<name>/v00X/` before a new submission overwrites them.
- **Private Settings in `.env`:** The Tractor host and credentials, the storage roots, the install paths and the artist machine map are read from a git-ignored `.env` file, never from the source code.
- **Modular PySide6 Front End:** A main window plus dedicated dialogs for the Tractor settings and the custom middle frame, sharing one dark purple stylesheet.

## Configuration
Copy `.env.example` to `.env` and fill in the values. The file is git-ignored and must never be committed. It is searched in the package folder, its parent folder and the repository root, or at the path stored in the `ATLAS_BATCHER_ENV` variable. Variables already set in the environment take precedence over the file.

| Key                  | Purpose                                                  |
|----------------------|----------------------------------------------------------|
| `TRACTOR_HOST`       | Tractor server URL                                       |
| `TRACTOR_USER`       | Tractor user used by the farm scanner                    |
| `TRACTOR_PASS`       | Tractor password used by the farm scanner                |
| `TRACTOR_ROOMS`      | Comma separated room numbers of the blade filter         |
| `ATLAS_SHOT_ROOT`    | Root folder of the shots                                 |
| `ATLAS_ASSET_ROOT`   | Root folder of the assets                                |
| `HUSK_PATH`          | Path of the husk executable                              |
| `HYTHON_PATH`        | Path of the hython executable                            |
| `TRACTOR_SPOOL_PATH` | Path of the tractor-spool executable                     |
| `ATLAS_USER_MAP`     | Comma separated `MACHINE_NAME:username` pairs            |

## Usage
```python
from atlas_batcher.ui.main import main

# Launch the Atlas Batcher window
main()
```

Pick a type (Lookdev, Shot or Custom), list the USD files, set the frame range, add them to the render list, then use **Local Render** or **Tractor**.

## Tests
The `core/` package is covered by a test suite that needs neither Houdini, Tractor nor PySide6: the Tractor server, the blade daemons, `husk`, `tractor-spool` and the file system are mocked, and every test runs against a fake `.env` instead of yours.

```bash
pip install -e ".[dev]"
pytest
```

## License
This project is licensed under the GNU General Public License v3.0 (GPL-3.0).

You are free to use, modify, and distribute this software under the terms of the GPL license.

See the full license text here: https://www.gnu.org/licenses/gpl-3.0.html

## Project Layout
```
atlas_batcher/
├── src/
│   └── atlas_batcher/        main python package root
│       ├── core/             render logic, zero UI dependencies
│       │   ├── env.py            .env settings loader
│       │   ├── render.py         render list and local rendering (husk)
│       │   ├── tractor.py        ALF creation and Tractor spooling
│       │   ├── tractor_scan.py   Tractor farm scanner (blade states, RAM, ping)
│       │   └── utils.py          paths, artist, shot / asset / USD discovery
│       └── ui/               PySide6 front end
│           ├── dialog/
│           │   ├── mid_frame_dialog.py   custom middle frame dialog
│           │   └── tractor_dialog.py     Tractor submission dialog
│           ├── icon/         UI icons and graphic assets
│           └── main.py       main window and entry point
├── tests/                    unit tests for core/ (Tractor, husk and file system mocked)
│   ├── conftest.py               package alias and isolated settings fixtures
│   ├── test_env.py
│   ├── test_render.py
│   ├── test_tractor.py
│   ├── test_tractor_scan.py
│   └── test_utils.py
├── .env                      private settings (git-ignored)
├── .env.example              template of the private settings
├── .gitignore
├── CONTRIBUTING.md
├── pyproject.toml
└── README.md
```

## Contributing
Bug reports, feature requests, and PRs are welcome — see
[`CONTRIBUTING.md`](CONTRIBUTING.md) for branch/commit conventions and
where new code should live.

## Notes
Please ensure proper environment setup (Houdini 20.5, Pixar Tractor 2.4, Python 3.11, PySide6) and a filled `.env` file before running the tool inside the Andhakara asset pipeline. The tool is imported as a plugin of Atlas Manager (`atlas_manager.plugins.batcher`), and a missing `.env` setting raises an explicit error naming the key.
