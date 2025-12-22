# Installation

## License and third-party software

- This repository contains a wrapper around CAT12 for research workflows.
- CAT12 / SPM12 / MATLAB Runtime (MCR) and other third-party tools are **downloaded by the installer** and are governed by their respective licenses.
- This repository does **not** distribute CAT12/SPM/MCR binaries.
- This project is **not affiliated with or endorsed by** the CAT12 or SPM developers, nor by The MathWorks.

See `THIRD_PARTY_NOTICES.md` in the repository root for details.

## System requirements

- Linux recommended (Ubuntu server works well)
- CPU: modern x86_64
- RAM: 8GB minimum, 16GB+ recommended (longitudinal + TFCE can be memory heavy)
- Disk: enough for the BIDS dataset + derivatives + stats outputs
- Tools: `bash`, `wget`, `unzip`, `curl`, `timeout`
- Python: 3.9+ recommended

## What gets installed (workspace-local)

The installer is designed to keep everything inside this repository:

- `external/cat12/`: CAT12 standalone + SPM12
- `external/MCR/`: MATLAB Runtime for CAT12 standalone
- `external/deno/`: Deno runtime (used by `bids-validator`)
- `.venv/`: Python virtual environment
- `.env`: environment variables consumed by wrappers

## Install

From the repo root:

### Option A: Standalone (No MATLAB license required)
```bash
./scripts/install_cat12_standalone.sh
```

### Option B: Existing MATLAB (Uses your local MATLAB installation)
```bash
./scripts/install_cat12_matlab.sh
```

That’s it. The wrappers (`./cat12_prepro`, `./cat12_stats`) will automatically activate `.venv` and source `.env`.

### Alternative: Makefile

```bash
make install         # For standalone
make install-matlab  # For existing MATLAB
make test
```

## Activate (optional)

You only need this if you want to run Python modules directly:

```bash
source activate_cat12.sh
```

## Notes on reproducibility

- Python dependencies are installed into `.venv`.
- CAT12 + MCR are installed into `external/`.
- No global installs are required.

## Common installation issues

- **Missing `wget` / `unzip` / `curl`**: install via your system package manager.
- **Corporate proxy / offline**: pre-download the CAT12 + MCR zips and adjust the installer URLs or place files into `external/` before running.
