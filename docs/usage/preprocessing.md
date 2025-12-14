# Usage — Preprocessing (`cat12_prepro`)

The preprocessing entrypoint is a BIDS App-style CLI that runs CAT12 standalone on a BIDS dataset.

- Wrapper: `./cat12_prepro`
- Implementation: `scripts/preprocessing/bids_cat12_processor.py` (Click CLI)

## Synopsis

```bash
./cat12_prepro <bids_dir> <output_dir> <analysis_level> [options]
```

### OpenNeuro input (optional)

You can download a public OpenNeuro dataset directly as the input by passing
`--openneuro`. In this mode, the `bids_dir` argument is interpreted as the
OpenNeuro dataset id (e.g., `ds003138`).

```bash
# Download a subset of subjects (recommended)
./cat12_prepro ds003138 /data/derivatives/cat12 participant \
  --openneuro --openneuro-tag 1.0.1 \
  --openneuro-dir /data/bids/ds003138 \
  --participant-label 01 --participant-label 02 \
  --preproc --no-surface

# Download all subjects (can be large)
./cat12_prepro ds003138 /data/derivatives/cat12 participant \
  --openneuro --openneuro-download-all \
  --preproc
```

Arguments:
- `bids_dir`: BIDS root directory
- `output_dir`: derivatives output directory
- `analysis_level`: `participant` (group is currently not implemented)

## Processing stages (opt-in)

You must specify at least one stage:

- `--preproc` — CAT12 preprocessing/segmentation
- `--smooth-volume ["6 8 10"]` — volume smoothing (FWHM in mm)
- `--smooth-surface ["12 15"]` — surface smoothing (FWHM in mm)
- `--qa` — quality assessment
- `--tiv` — total intracranial volume estimates
- `--roi` — ROI extraction

Notes:
- `--smooth-volume` / `--smooth-surface` accept **space-separated kernels**. Multiple kernels produce multiple outputs (e.g. `s6…`, `s8…`).
- If you pass the flag without explicit values, the implementation falls back to defaults (volume: 6mm, surface: 12mm).

## Selection options

- `--participant-label <ID>` — process only specific participants
  - Accepts `01` or `sub-01`
  - Repeat the flag for multiple participants (e.g., `--participant-label 01 --participant-label 02`)
- `--session-label <SES>` — process only specific sessions
  - Repeat the flag for multiple sessions (e.g., `--session-label 01 --session-label 02`)
- `--cross` — force cross-sectional processing (use first available session per subject)
- `--pilot` — randomly pick a single participant (useful for a smoke test)

## Execution options

- `--config <file>` — config file (`.json`, `.yml`, `.yaml`)
- `--no-surface` — skip surface extraction during preprocessing
- `--no-validate` — skip BIDS validation
- `--n-jobs <N|auto>` — parallel subject processing
  - `auto`: choose based on RAM (4GB/job, reserve 16GB)
- `--work-dir <path>` — temp/work directory
- `--log-dir <path>` — where logs are written (default: `<output_dir>/logs`)
- `--verbose` — verbose logging
- `--nohup` — detach and write to `nohup.out` (handy for SSH sessions)

## Examples

### Minimal preprocessing (auto longitudinal detection)

```bash
./cat12_prepro /data/bids /data/derivatives/cat12 participant --preproc
```

### Volume-only preprocessing

```bash
./cat12_prepro /data/bids /data/derivatives/cat12 participant --preproc --no-surface
```

### Full preprocessing + QA + TIV

```bash
./cat12_prepro /data/bids /data/derivatives/cat12 participant --preproc --qa --tiv
```

### Parallel processing (automatic job count)

```bash
./cat12_prepro /data/bids /data/derivatives/cat12 participant --preproc --n-jobs auto
```

### Multiple smoothing kernels

```bash
./cat12_prepro /data/bids /data/derivatives/cat12 participant \
  --preproc \
  --smooth-volume "6 8 10" \
  --smooth-surface "12 15"
```

## Help

```bash
./cat12_prepro --help
```
