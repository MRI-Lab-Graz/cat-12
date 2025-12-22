# Usage — Longitudinal statistics (`cat12_stats`)

The statistics entrypoint runs a longitudinal group analysis on CAT12 outputs and can optionally run TFCE correction.

- Wrapper: `./cat12_stats`
- Implementation: `scripts/stats/cat12_longitudinal_analysis.sh`

## Two invocation modes

### 1) Standard mode (recommended)

```bash
./cat12_stats --cat12-dir <path> --participants <participants.tsv> [options]
```

### 2) Reproduction mode

```bash
./cat12_stats --design <design.json> [options]
```

This is intended to reproduce a previously generated analysis (same model/contrasts).

## Required arguments

Standard mode:
- `--cat12-dir <path>`: preprocessing output directory (CAT12 derivatives)
- `--participants <tsv>`: BIDS `participants.tsv`

Reproduction mode:
- `--design <json>`: design file written by a previous run

## Analysis options

- `--modality <name>`: `vbm` (default), `thickness`, `depth`, `gyrification`, `fractal`
- `--smoothing <mm>`: smoothing kernel; if omitted the pipeline attempts to auto-detect
- `--analysis-name <name>`: override the auto-generated analysis name
- `--output-dir <path>` / `--output <path>`: where results are written

## Design options

- `--group-col <name>`: group column in `participants.tsv` (auto-detect if omitted)
- `--session-col <name>`: session column (default: `session`)
- `--sessions <list>`: `all` or a comma-separated list like `"1,2,3"`
- `--covariates <list>`: comma-separated covariate columns (e.g. `"age,sex,tiv"`)

## Screening options

- `--uncorrected-p <p>`: screening p-value (default from `config/config.ini`)
- `--cluster-size <k>`: minimum cluster size (default from `config/config.ini`)

## TFCE options

- `--n-perm <N>` / `--nperms <N>`: number of permutations
- `--pilot`: pilot mode (sets permutations to 100)
- `--skip-screening`: run TFCE on all contrasts (not recommended)
- `--no-tfce`: stop after screening (skip TFCE correction)
- `--n-jobs <N>`: parallel jobs for TFCE

## Other options

- `--config <file>`: custom `config.ini`
- `--force`: delete existing results dir before starting
- `--nohup`: detach and log to `cat12_stats_<timestamp>.log` (wrapper or script)
- `--help` / `-h`: show help

## Output layout

If `--output-dir` is not provided, results are written under:

- `scripts/stats/results/<modality>/<analysis_name>/`

Each run writes a pipeline log:

- `.../logs/pipeline.log`

## Examples

### Basic VBM

```bash
./cat12_stats \
  --cat12-dir /data/derivatives/cat12 \
  --participants /data/bids/participants.tsv
```

### Thickness with covariates

```bash
./cat12_stats \
  --cat12-dir /data/derivatives/cat12 \
  --participants /data/bids/participants.tsv \
  --modality thickness \
  --smoothing 15 \
  --covariates "age,sex,tiv"
```

### Pilot run

```bash
./cat12_stats \
  --cat12-dir /data/derivatives/cat12 \
  --participants /data/bids/participants.tsv \
  --pilot
```

### Background run

```bash
./cat12_stats \
  --cat12-dir /data/derivatives/cat12 \
  --participants /data/bids/participants.tsv \
  --nohup
```

## Help

```bash
./cat12_stats --help
```

## Configuration defaults

Many defaults come from `config/config.ini` and can be overridden by flags.

## Post-Stats Reporting

After the analysis is complete, you can generate a comprehensive HTML report summarizing the significant results.

```bash
./.venv/bin/python scripts/stats/post_stats_report.py /path/to/results/folder
```

This script will:
- Check for significant voxels at multiple thresholds ($p < 0.01$, $p < 0.05$, $p < 0.1$).
- Summarize results for FWE, FDR, and Uncorrected maps.
- Map peak coordinates to anatomical regions using the **AAL3 atlas**.
- Generate a color-coded HTML report for easy review.
