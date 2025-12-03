#!/bin/bash
#
# CAT12 Longitudinal Analysis Pipeline
# =====================================
#
# Complete automated workflow from CAT12 preprocessing to TFCE-corrected results.
# Production Ready - Reviewed 2025-12-03
#
# USAGE:
#   ./cat12_longitudinal_analysis.sh --cat12-dir <path> --participants <tsv> [options]
#   ./cat12_longitudinal_analysis.sh --design <json> [options]
#
# REQUIRED ARGUMENTS (Standard Mode):
#   --cat12-dir <path>      Path to CAT12 preprocessing output directory
#   --participants <tsv>    Path to BIDS participants.tsv file
#
# REQUIRED ARGUMENTS (Reproduction Mode):
#   --design <json>         Path to design.json file (reproduces exact analysis)
#
# ANALYSIS OPTIONS:
#   --modality <name>       Analysis type: vbm, thickness, depth, gyrification, fractal
#                           (default: vbm)
#   --smoothing <mm>        Smoothing kernel in mm (default: auto-detect)
#   --analysis-name <name>  Custom name for analysis (default: auto-generated)
#   --output-dir <path> / --output <path>
#                           Custom output directory (overrides default location)
#
# DESIGN OPTIONS:
#   --group-col <name>      Column name for group variable in participants.tsv
#   --session-col <name>    Column name for session variable (default: session)
#   --sessions <list>       Sessions to include: "all" or "1,2,3" (default: all)
#   --covariates <list>     Comma-separated covariate columns (e.g., "age,sex,tiv")
#
# TFCE OPTIONS:
#   --n-perm <N> / --nperms <N>
#                         Number of TFCE permutations (default: 5000)
#   --pilot                Run pilot mode (100 permutations, 1 contrast)
#   --skip-screening       Run TFCE on all contrasts (not recommended)
#   --no-tfce              Stop after screening (skip TFCE correction)
#
# Behavior note: the pipeline now runs TFCE in an automatic two-stage
# probe-then-full strategy by default (a short probe run is performed to
# inspect the permutation diagnostic `cc` and the full run will switch to
# Freedman–Lane nuisance handling if the probe indicates instability). No
# additional CLI flag is required to enable this behavior.
#
# SCREENING OPTIONS:
#   --cluster-size <k>     Minimum cluster size for screening (default: 50)
#   --uncorrected-p <p>    Uncorrected p-value threshold for screening (default: 0.001)
#
# OTHER OPTIONS:
#   --config <file>        Path to custom config.ini file
#   --force                Delete existing results directory before starting
#   --n-jobs <N>           Parallel jobs for TFCE (default: 4)
#
# EXAMPLES:
#
#   # Basic VBM analysis with 6mm smoothing and sessions 1,3
#   ./cat12_longitudinal_analysis.sh \
#       --cat12-dir /data/cat12 \
#       --participants /data/participants.tsv \
#       --smoothing 6 \
#       --sessions "1,3"
#
#   # Cortical thickness with covariates
#   ./cat12_longitudinal_analysis.sh \
#       --cat12-dir /data/cat12 \
#       --participants /data/participants.tsv \
#       --modality thickness \
#       --smoothing 20 \
#       --covariates "age,sex,tiv"

set -euo pipefail

# Capture original arguments early so we can safely reconstruct the exact
# command line later (avoids issues with unmatched quotes when we pass the
# command line into reports). Store as array to preserve spacing and quoting.
ORIGINAL_ARGS=("$@")

# Capture pipeline start time for filtering old results
PIPELINE_START_TIME=$(date +%s)

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
STATS_DIR="$SCRIPT_DIR"

# ============================================================================
# Load Configuration from config.ini
# ============================================================================

# Default config file
CONFIG_FILE="$STATS_DIR/config.ini"

# Pre-parse for --config flag to load correct defaults
args=("$@")
for ((i=0; i<$#; i++)); do
    if [[ "${args[i]}" == "--config" ]]; then
        next_index=$((i+1))
        if [[ $next_index -lt $# ]]; then
            CONFIG_FILE="${args[next_index]}"
        fi
        break
    fi
done

# Function to read INI values
get_ini_value() {
    local section="$1"
    local key="$2"
    local default="$3"
    
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "$default"
        return
    fi
    
    local value=$(awk -F '=' -v section="[$section]" -v key="$key" '
        /^\[/ { current_section = $0 }
        current_section == section && $1 ~ /^[[:space:]]*'"$key"'[[:space:]]*$/ {
            val = $2
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
            print val
            exit
        }
    ' "$CONFIG_FILE")
    
    if [[ -z "$value" ]]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Load configuration defaults from config.ini
MATLAB_EXE=$(get_ini_value "MATLAB" "exe" "/Applications/MATLAB_R2025b.app/bin/matlab")
SPM_PATH=$(get_ini_value "SPM" "path" "")
PYTHON_EXE=$(get_ini_value "PYTHON" "exe" "python3")

# Allow graphics windows in MATLAB? If true we omit -nodisplay. If false we add -nodisplay
MATLAB_ALLOW_GRAPHICS=$(get_ini_value "MATLAB" "allow_graphics" "true")


MODALITY=$(get_ini_value "ANALYSIS" "modality" "vbm")
SMOOTHING=$(get_ini_value "ANALYSIS" "smoothing" "")
GROUP_COL=$(get_ini_value "ANALYSIS" "group_col" "")
SESSION_COL=$(get_ini_value "ANALYSIS" "session_col" "session")
SESSIONS=$(get_ini_value "ANALYSIS" "sessions" "all")
COVARIATES=$(get_ini_value "ANALYSIS" "covariates" "")
STANDARDIZE_CONTINUOUS=$(get_ini_value "ANALYSIS" "standardize_continuous_variables" "false")

UNCORRECTED_P=$(get_ini_value "SCREENING" "uncorrected_p" "0.01")
CLUSTER_SIZE=$(get_ini_value "SCREENING" "cluster_size" "50")
SKIP_SCREENING=$(get_ini_value "SCREENING" "skip_screening" "false")

N_PERM=$(get_ini_value "TFCE" "n_perm" "5000")
PILOT_MODE=$(get_ini_value "TFCE" "pilot_mode" "false")
NO_TFCE=false

# Two-stage TFCE probe parameters (automatic, no CLI flag required)
# initial_perm: quick probe run to estimate cc (default: 100)
# cc_threshold: if probe cc < threshold, use Freedman-Lane for full run
INITIAL_PERM=$(get_ini_value "TFCE" "initial_perm" "100")
CC_THRESHOLD=$(get_ini_value "TFCE" "cc_threshold" "0.98")

N_JOBS=$(get_ini_value "PERFORMANCE" "parallel_jobs" "4")

OUTPUT_DIR=$(get_ini_value "OUTPUT" "output_dir" "")
ANALYSIS_NAME=$(get_ini_value "OUTPUT" "analysis_name" "")
FORCE=$(get_ini_value "OUTPUT" "force_clean" "false")

# Safety check: If OUTPUT_DIR is the same as CAT12_DIR, abort immediately
if [[ -n "$OUTPUT_DIR" ]] && [[ -n "$CAT12_DIR" ]]; then
    # Normalize paths for comparison
    ABS_OUTPUT=$(cd "$OUTPUT_DIR" 2>/dev/null && pwd || echo "$OUTPUT_DIR")
    ABS_CAT12=$(cd "$CAT12_DIR" 2>/dev/null && pwd || echo "$CAT12_DIR")
    
    if [[ "$ABS_OUTPUT" == "$ABS_CAT12" ]]; then
        echo "CRITICAL ERROR: Output directory cannot be the same as CAT12 input directory!"
        echo "  Input:  $ABS_CAT12"
        echo "  Output: $ABS_OUTPUT"
        echo "This would overwrite/delete your input data."
        exit 1
    fi
fi

# Auto-detect MATLAB if empty in config
USE_STANDALONE=false

# Check if configured MATLAB_EXE exists
if [[ ! -x "$MATLAB_EXE" ]] && ! command -v "$MATLAB_EXE" &> /dev/null; then
    # Configured MATLAB not found. Try auto-detection.
    # Use '|| true' to prevent script exit if find fails (e.g. /Applications missing on Linux)
    FOUND_MATLAB=$(find /Applications -name "MATLAB_R*.app" -maxdepth 1 2>/dev/null | sort -r | head -1 || true)
    if [[ -n "$FOUND_MATLAB" ]]; then
        MATLAB_EXE="$FOUND_MATLAB/bin/matlab"
    elif command -v matlab &> /dev/null; then
        MATLAB_EXE="matlab"
    else
        # Fallback to standalone
        echo "MATLAB executable not found at configured path or in PATH."
        echo "Switching to CAT12 Standalone mode."
        USE_STANDALONE=true
        MATLAB_EXE="standalone"
    fi
fi

# Function to run MATLAB commands (via MATLAB or Standalone)
run_matlab() {
    local cmd="$1"
    if [[ "$USE_STANDALONE" == "true" ]]; then
        # Use the Python wrapper for standalone
        # We assume run_matlab_standalone.py is in STATS_DIR
        "$PYTHON_EXE" "$STATS_DIR/run_matlab_standalone.py" --utils "$STATS_DIR/utils" "$cmd"
    else
        "$MATLAB_EXE" $MATLAB_FLAGS "$cmd"
    fi
}

if [[ "$USE_STANDALONE" == "true" ]]; then
    UTILS_PATH_CMD=""
else
    UTILS_PATH_CMD="addpath('$STATS_DIR/utils');"
fi

# Check for Python 3
if ! command -v "$PYTHON_EXE" &> /dev/null; then
    echo "Error: Python executable '$PYTHON_EXE' not found."
    echo "Please install Python 3 or update [PYTHON] exe in config.ini."
    exit 1
fi

# Build MATLAB flags depending on whether graphics are allowed
if [[ "$MATLAB_ALLOW_GRAPHICS" == "false" ]] || [[ "$MATLAB_ALLOW_GRAPHICS" == "0" ]]; then
    MATLAB_FLAGS="-nodesktop -nodisplay -nosplash -batch"
else
    # Allow graphics (still run non-interactively via -batch). Omitting -nodisplay
    # allows figure creation on systems with a display (or XQuartz on macOS).
    MATLAB_FLAGS="-nodesktop -nosplash -batch"
fi

# ============================================================================
# Default Parameters (for values not in config)
# ============================================================================

CAT12_DIR=""
PARTICIPANTS_FILE=""
DESIGN_FILE=""

# Show help if no arguments provided
if [[ $# -eq 0 ]]; then
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════╗"
    echo "║              CAT12 Longitudinal Analysis Pipeline                      ║"
    echo "╚════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "USAGE:"
    echo "  $0 --cat12-dir <path> --participants <tsv> [options]"
    echo "  $0 --design <json> [options]"
    echo ""
    echo "REQUIRED ARGUMENTS (Standard Mode):"
    echo "  --cat12-dir <path>      Path to CAT12 preprocessing output"
    echo "  --participants <tsv>    Path to BIDS participants.tsv file"
    echo ""
    echo "REQUIRED ARGUMENTS (Reproduction Mode):"
    echo "  --design <json>         Path to design.json file"
    echo ""
    echo "ANALYSIS OPTIONS:"
    echo "  --modality <name>       vbm (default), thickness, depth, gyrification, fractal"
    echo "  --smoothing <mm>        Smoothing kernel (default: auto-detect)"
    echo "  --analysis-name <name>  Custom analysis name (default: auto-generated)"
    echo "  --output-dir <path> / --output <path>"
    echo "                          Custom output directory (overrides default location)"
    echo "  --group-col <name>      Group column in participants.tsv (auto-detect if omitted)"
    echo "  --covariates <list>     Covariates: age,sex,tiv (optional)"
    echo ""
    echo "TFCE OPTIONS:"
    echo "  --n-perm <N>            TFCE permutations (default: 5000)"
    echo "  --pilot                 Quick test mode (100 permutations)"
    echo "  --skip-screening        Run TFCE on all contrasts (not recommended)"
    echo "  --no-tfce               Stop after screening (skip TFCE correction)"
    echo ""
    echo "SCREENING OPTIONS:"
    echo "  --uncorrected-p <p>     P-value threshold (default: 0.001)"
    echo "  --cluster-size <k>      Minimum cluster size (default: 50 voxels)"
    echo ""
    echo "OTHER OPTIONS:"
    echo "  --config <file>         Path to custom config.ini file"
    echo "  --force                 Delete existing results before starting"
    echo "  --n-jobs <N>            Parallel jobs for TFCE (default: 4)"
    echo "  --help, -h              Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo ""
    echo "  # Basic VBM analysis"
    echo "  $0 --cat12-dir /data/cat12 --participants participants.tsv"
    echo ""
    echo "  # Quick test"
    echo "  $0 --cat12-dir /data/cat12 --participants participants.tsv --pilot"
    echo ""
    echo "  # With covariates"
    echo "  $0 --cat12-dir /data/cat12 --participants participants.tsv \\"
    echo "     --covariates \"age,sex,tiv\""
    echo ""
    echo "  # Cortical thickness"
    echo "  $0 --cat12-dir /data/cat12 --participants participants.tsv \\"
    echo "     --modality thickness"
    echo ""
    echo "CONFIGURATION:"
    echo "  Edit config.ini to customize defaults for:"
    echo "    - MATLAB and SPM paths"
    echo "    - Analysis parameters (n_perm, uncorrected_p, cluster_size)"
    echo "    - Performance settings (parallel_jobs)"
    echo ""
    echo "  Command-line arguments override config.ini values."
    echo ""
    echo "RESULTS:"
    echo "  Saved to: results/<modality>/<analysis_name>/"
    echo "  - report.html          Interactive analysis report"
    echo "  - spm_batch.m          SPM batch file (for reproducibility)"
    echo "  - SPM.mat              Statistical model"
    echo "  - TFCE_*_fwe.nii       FWE-corrected results"
    echo ""
    echo "════════════════════════════════════════════════════════════════════════"
    echo ""
    exit 0
fi

# ============================================================================
# Parse Arguments
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            # Handled in pre-parse loop, just skip
            shift 2
            ;;
        --cat12-dir)
            CAT12_DIR="$2"
            shift 2
            ;;
        --participants)
            PARTICIPANTS_FILE="$2"
            shift 2
            ;;
        --design)
            DESIGN_FILE="$2"
            shift 2
            ;;
        --modality)
            MODALITY="$2"
            shift 2
            ;;
        --smoothing)
            SMOOTHING="$2"
            shift 2
            ;;
        --analysis-name)
            ANALYSIS_NAME="$2"
            shift 2
            ;;
        --output-dir|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --group-col)
            GROUP_COL="$2"
            shift 2
            ;;
        --session-col)
            SESSION_COL="$2"
            shift 2
            ;;
        --sessions)
            SESSIONS="$2"
            shift 2
            ;;
        --covariates)
            COVARIATES="$2"
            shift 2
            ;;
        --n-perm|--nperms)
            N_PERM="$2"
            shift 2
            ;;
        --pilot)
            PILOT_MODE=true
            N_PERM=100
            shift
            ;;
        --skip-screening)
            SKIP_SCREENING=true
            shift
            ;;
        --no-tfce)
            NO_TFCE=true
            shift
            ;;
        --cluster-size)
            CLUSTER_SIZE="$2"
            shift 2
            ;;
        --uncorrected-p)
            UNCORRECTED_P="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --n-jobs)
            N_JOBS="$2"
            shift 2
            ;;
        --help|-h)
            # Print the top-of-file help header
            grep "^#" "$0" | tail -n +3

            # Also extract CLI flags declared in utility scripts under utils/
            echo ""
            echo "────────────────────────────────────────────────────────────────────────" 
            echo "Additional flags exposed by helper scripts in ./utils/ (extracted):"
            echo "(Showing raw add_argument(...) entries from each utils/*.py file)"
            echo ""
            for f in "$STATS_DIR"/utils/*.py; do
                if [[ -f "$f" ]]; then
                    echo "== $(basename "$f") =="
                    # print add_argument contents, one-per-line (safe text extraction)
                    grep -E "add_argument\(" "$f" 2>/dev/null | sed -E "s/.*add_argument\(([^)]*)\).*/  \1/" | sed -E "s/^[[:space:]]*//;s/[[:space:]]+/ /g" || true
                    echo ""
                fi
            done
            exit 0
            ;;
        *)
            echo "Error: Unknown argument: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# Validation
# ============================================================================

if [[ -n "$DESIGN_FILE" ]]; then
    if [[ ! -f "$DESIGN_FILE" ]]; then
        echo "Error: Design file not found: $DESIGN_FILE"
        exit 1
    fi
else
    if [[ -z "$CAT12_DIR" ]] || [[ -z "$PARTICIPANTS_FILE" ]]; then
        echo "Error: Missing required arguments"
        echo "Usage: $0 --cat12-dir <path> --participants <tsv>"
        echo "   OR: $0 --design <json_file>"
        echo "Run: $0 --help   for full help"
        exit 1
    fi
fi

if [[ -n "$CAT12_DIR" ]] && [[ ! -d "$CAT12_DIR" ]]; then
    echo "Error: CAT12 directory not found: $CAT12_DIR"
    exit 1
fi

if [[ -n "$PARTICIPANTS_FILE" ]] && [[ ! -f "$PARTICIPANTS_FILE" ]]; then
    echo "Error: Participants file not found: $PARTICIPANTS_FILE"
    exit 1
fi

# Make paths absolute
if [[ -n "$CAT12_DIR" ]]; then
    CAT12_DIR="$(cd "$CAT12_DIR" && pwd)"
fi
if [[ -n "$PARTICIPANTS_FILE" ]]; then
    PARTICIPANTS_FILE="$(cd "$(dirname "$PARTICIPANTS_FILE")" && pwd)/$(basename "$PARTICIPANTS_FILE")"
fi
if [[ -n "$DESIGN_FILE" ]]; then
    DESIGN_FILE="$(cd "$(dirname "$DESIGN_FILE")" && pwd)/$(basename "$DESIGN_FILE")"
fi

# Auto-detect smoothing if not specified
if [[ -z "$SMOOTHING" ]]; then
    # Find one representative mwp1r file under the supplied CAT12 dir and
    # try to extract the smoothing kernel (e.g. 's6mwp1r' -> 6). If no
    # smoothing prefix is present, fall back to default 6 mm.
    if [[ -n "$CAT12_DIR" ]]; then
        FOUND_FILE=$(find "$CAT12_DIR" -type f -iname "*mwp1r*.nii*" 2>/dev/null | head -n 1 || true)
        if [[ -n "$FOUND_FILE" ]]; then
            basefn=$(basename "$FOUND_FILE")
            if [[ "$basefn" =~ s([0-9]+)mwp1r ]]; then
                SMOOTHING="${BASH_REMATCH[1]}"
            else
                # No explicit smoothing prefix found in filename; default to 6
                SMOOTHING="6"
            fi
        else
            SMOOTHING="6"
        fi
    else
        SMOOTHING="6"
    fi
fi

# Set default analysis name if not provided
if [[ -z "$ANALYSIS_NAME" ]]; then
    ANALYSIS_NAME="${MODALITY}_smooth_auto"
fi

# Set results directory
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$STATS_DIR/results/${MODALITY}/${ANALYSIS_NAME}"
else
    OUTPUT_DIR="$(cd "$(dirname "$OUTPUT_DIR")" && pwd)/$(basename "$OUTPUT_DIR")"
fi

# Ensure output dir exists early so we can capture logs there
mkdir -p "$OUTPUT_DIR"

# Start capturing terminal output to a pipeline log inside the results folder
LOG_DIR="$OUTPUT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline.log"
# tee all stdout/stderr to the log file (append)
exec > >(tee -a "$LOG_FILE") 2>&1

# Create temp directory
TEMP_DIR=$(mktemp -d "$STATS_DIR/.tmp_${ANALYSIS_NAME}_XXXXXX")
trap "rm -rf '$TEMP_DIR'" EXIT

# ============================================================================
# Banner
# ============================================================================

cat << 'EOF'

╔════════════════════════════════════════════════════════════════════════╗
║              CAT12 Longitudinal Analysis Pipeline                      ║
╚════════════════════════════════════════════════════════════════════════╝

EOF

echo "Configuration:"
echo "  CAT12 directory:    $CAT12_DIR"
echo "  Participants file:  $PARTICIPANTS_FILE"
echo "  Modality:           $MODALITY"
echo "  Smoothing:          ${SMOOTHING}mm"
echo "  Analysis name:      $ANALYSIS_NAME"
echo "  Results directory:  $OUTPUT_DIR"
echo ""
echo "Design:"
echo "  Group column:       ${GROUP_COL:-auto-detect}"
echo "  Session column:     $SESSION_COL"
echo "  Sessions:           $SESSIONS"
echo "  Covariates:         ${COVARIATES:-none}"
echo ""
echo "TFCE:"
echo "  Permutations:       $N_PERM"
echo "  Pilot mode:         $PILOT_MODE"
echo "  Skip screening:     $SKIP_SCREENING"
echo "  Parallel jobs:      $N_JOBS"
echo ""
echo "Options:"
echo "  Force clean:        $FORCE"
echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# ============================================================================
# One-time SPM configuration step
# Run configure_spm_path once early so subsequent MATLAB calls don't re-run the
# interactive/config detection tool and clutter the logs.
# ============================================================================
echo "Checking SPM configuration (one-time)..."
MATLAB_SPM_LOG="$LOG_DIR/matlab_configure_spm.log"
if [[ "$USE_STANDALONE" == "false" ]]; then
    run_matlab "$UTILS_PATH_CMD try, configure_spm_path; catch e, fprintf('Warning: configure_spm_path failed: %s\n', e.message); end;" 2>&1 | tee -a "$MATLAB_SPM_LOG" || {
        echo "Warning: one-time SPM configuration step failed (see $MATLAB_SPM_LOG). Continuing, but later MATLAB calls may need SPM path set."
    }
else
    echo "Skipping SPM configuration (Standalone mode)."
fi
echo ""

# ============================================================================
# Step 0: Clean existing results if --force
#
# When --force is provided we remove the full results directory and any
# temporary directories left from previous runs. For safety we only allow a
# full recursive removal when the target is under "$STATS_DIR/results".
# If the output directory is outside that location we remove only its
# contents to avoid accidental deletion of unrelated paths.
# ============================================================================

if [[ "$FORCE" == true ]]; then
    if [[ -d "$OUTPUT_DIR" ]]; then
        # Safety: allow full rm -rf only for expected results locations
        case "$OUTPUT_DIR" in
            "$STATS_DIR"/results/*)
                echo "Removing entire results directory: $OUTPUT_DIR"
                rm -rf "$OUTPUT_DIR"
                echo "✓ Removed $OUTPUT_DIR"
                ;;
            *)
                echo "Warning: OUTPUT_DIR ($OUTPUT_DIR) is outside expected results path."
                echo "Skipping automatic cleanup to prevent accidental data loss."
                echo "Please manually clean the output directory if needed."
                ;;
        esac
    else
        echo "No existing results directory to remove: $OUTPUT_DIR"
    fi

    # Remove any stale temporary directories for this analysis
    TMP_PATTERN="$STATS_DIR/.tmp_${ANALYSIS_NAME}_*"
    shopt -s nullglob
    tmpdirs=( $TMP_PATTERN )
    for d in "${tmpdirs[@]:-}"; do
        if [[ "$d" != "$TEMP_DIR" ]]; then
            echo "Removing stale temp directory: $d"
            rm -rf "$d"
        fi
    done
    shopt -u nullglob

    echo ""
fi

# ============================================================================
# Step 1: Parse Participants & Design
# ============================================================================

echo "┌────────────────────────────────────────────────────────────────────────┐"
echo "│ STEP 0: PREFLIGHT CHECKS (Python packages, CAT12 files, participants)  │"
echo "└────────────────────────────────────────────────────────────────────────┘"
echo ""

if [[ -n "$CAT12_DIR" ]] && [[ -n "$PARTICIPANTS_FILE" ]]; then
    PREFLIGHT_ARGS=""
    if [[ "$USE_STANDALONE" == "true" ]]; then
        PREFLIGHT_ARGS="--standalone"
    fi
    python3 "$STATS_DIR/utils/preflight_check.py" --cat12-dir "$CAT12_DIR" --participants "$PARTICIPANTS_FILE" --smoothing "$SMOOTHING" --modality "$MODALITY" $PREFLIGHT_ARGS || {
        echo "Error: Preflight checks failed. Fix issues above and re-run."
        exit 1
    }
else
    echo "Skipping preflight checks (CAT12_DIR or PARTICIPANTS_FILE not provided)."
fi


echo "┌────────────────────────────────────────────────────────────────────────┐"
echo "│ STEP 1: Parsing Participants File                                     │"
echo "└────────────────────────────────────────────────────────────────────────┘"
echo ""

if [[ -n "$DESIGN_FILE" ]]; then
    echo "Using provided design file: $DESIGN_FILE"
    cp "$DESIGN_FILE" "$TEMP_DIR/design.json"
else
    # If modality is thickness, drop TIV as a covariate even if the user
    # requested it. TIV is not an appropriate covariate for cortical
    # thickness and would remove the effect of interest.
    if [[ "$MODALITY" == "thickness" && -n "$COVARIATES" ]]; then
        COVARIATES=$(python3 - <<PY
cov_str = "${COVARIATES}"
parts = [c.strip() for c in cov_str.split(',') if c.strip().lower() != 'tiv']
print(','.join(parts))
PY
)
        if [[ -z "$COVARIATES" ]]; then
            echo "Thickness modality: removed TIV from covariates; no covariates remain."
        else
            echo "Thickness modality: removed TIV from covariates. Using: $COVARIATES"
        fi
    fi

    python3 "$STATS_DIR/utils/parse_participants.py" \
        --cat12-dir "$CAT12_DIR" \
        --participants "$PARTICIPANTS_FILE" \
        --modality "$MODALITY" \
        --smoothing "$SMOOTHING" \
        --output "$TEMP_DIR" \
        ${GROUP_COL:+--group-col "$GROUP_COL"} \
        --session-col "$SESSION_COL" \
        --sessions "$SESSIONS" \
        ${COVARIATES:+--covariates "$COVARIATES"} \
        ${STANDARDIZE_CONTINUOUS:+--standardize-continuous} || {
            echo "Error: Failed to parse participants file"
            exit 1
        }
fi

echo ""

# Persist design.json into the results folder so reports can be generated even
# if temporary directories are cleaned up (helps when --force is used).
if [[ -f "$TEMP_DIR/design.json" ]]; then
    mkdir -p "$OUTPUT_DIR"
    cp "$TEMP_DIR/design.json" "$OUTPUT_DIR/design.json"
    echo "Design JSON copied to: $OUTPUT_DIR/design.json"
fi

# If covariates were resolved in the design, append them to the analysis name
# so output folders reflect covariate usage (e.g., vbm_smooth_auto_tiv)
if [[ -f "$TEMP_DIR/design.json" ]]; then
    COV_LIST=$(python3 - <<PY
import json
d=json.load(open('$TEMP_DIR/design.json'))
covs=list(d.get('covariates',{}).keys())
print(','.join(covs))
PY
)
    if [[ -n "$COV_LIST" ]]; then
        # convert comma-separated to underscore-separated suffix
        COV_SUFFIX=$(echo "$COV_LIST" | sed 's/,/_/g')
        NEW_ANALYSIS_NAME="${ANALYSIS_NAME}_${COV_SUFFIX}"
        NEW_OUTPUT_DIR="$STATS_DIR/results/${MODALITY}/${NEW_ANALYSIS_NAME}"
        if [[ "$NEW_OUTPUT_DIR" != "$OUTPUT_DIR" ]]; then
            # Ensure parent exists
            mkdir -p "$(dirname "$NEW_OUTPUT_DIR")"
            # Move current output dir to new name (keep existing logs/files)
            mv "$OUTPUT_DIR" "$NEW_OUTPUT_DIR" 2>/dev/null || true
            OUTPUT_DIR="$NEW_OUTPUT_DIR"
            ANALYSIS_NAME="$NEW_ANALYSIS_NAME"
            LOG_DIR="$OUTPUT_DIR/logs"
            LOG_FILE="$LOG_DIR/pipeline.log"
            echo "Renamed results folder to include covariates: $OUTPUT_DIR"
        fi
    fi
fi

    # Generate an ASCII preview of the design matrix and save it to results
    if [[ -f "$OUTPUT_DIR/design.json" ]]; then
        echo "Generating ASCII design-matrix preview (text)..."
        python3 "$STATS_DIR/utils/print_design_ascii.py" "$OUTPUT_DIR/design.json" --output "$OUTPUT_DIR/design_ascii.txt" --rows 20 || {
            echo "⚠️  Warning: ASCII design preview generation failed"
        }
        if [[ -f "$OUTPUT_DIR/design_ascii.txt" ]]; then
            echo "--- Design ASCII preview (first lines) ---"
            head -n 30 "$OUTPUT_DIR/design_ascii.txt" || true
            echo "-----------------------------------------"
        fi
    fi

# ============================================================================
# Step 2a: Explicit mask handling
# ============================================================================

# For cortical thickness (surface-based GIfTI analysis) we do not use an
# explicit volumetric GM mask. The design/batch utilities will instead work
# directly with surface files.
MASK_FILE=""

if [[ "$MODALITY" != "thickness" ]]; then
    # For non-thickness modalities we prefer the repo-level canonical CAT12
    # tight brainmask located at templates/brainmask_GMtight.nii (or an
    # override from config.ini) to keep masking consistent across analyses.
    GM_MASK_CONFIG=$(get_ini_value "MASKING" "gm_mask" "")
    if [[ -n "$GM_MASK_CONFIG" ]]; then
        if [[ "$GM_MASK_CONFIG" = /* ]]; then
            TEMPLATE_MASK="$GM_MASK_CONFIG"
        else
            TEMPLATE_MASK="$STATS_DIR/$GM_MASK_CONFIG"
        fi
    else
        TEMPLATE_MASK="$STATS_DIR/templates/brainmask_GMtight.nii"
    fi

    if [[ -f "$TEMPLATE_MASK" ]]; then
        echo "Using GM mask: $TEMPLATE_MASK"
        MASK_FILE="$TEMPLATE_MASK"
    else
        echo "No GM mask found at $TEMPLATE_MASK — running without an explicit mask"
        MASK_FILE=""
    fi
else
    echo "Thickness modality detected – running without an explicit GM mask"
fi


# ============================================================================
# Step 2b: Generate SPM Batch File
# ============================================================================

echo "┌────────────────────────────────────────────────────────────────────────┐"
echo "│ STEP 2b: Generating SPM Factorial Design                              │"
echo "└────────────────────────────────────────────────────────────────────────┘"
echo ""

MASK_ARG=""
if [[ -n "$MASK_FILE" ]]; then
    MASK_ARG="--mask-file $MASK_FILE"
fi

python3 "$STATS_DIR/utils/generate_spm_batch.py" \
    --design-file "$TEMP_DIR/design.json" \
    --output-dir "$OUTPUT_DIR" \
    --modality "$MODALITY" \
    --output "$TEMP_DIR/spm_batch.m" \
    $MASK_ARG || {
        echo "Error: Failed to generate SPM batch"
        exit 1
    }

# Copy batch file to output directory for reproducibility
cp "$TEMP_DIR/spm_batch.m" "$OUTPUT_DIR/spm_batch.m"
echo "✓ SPM batch file generated and saved to: $OUTPUT_DIR/spm_batch.m"
echo ""

# ============================================================================
# Step 3: Run Model Estimation
# ============================================================================

echo "┌────────────────────────────────────────────────────────────────────────┐"
echo "│ STEP 3: SPM Model Estimation                                          │"
echo "└────────────────────────────────────────────────────────────────────────┘"
echo ""

mkdir -p "$OUTPUT_DIR"

# Delete any existing SPM.mat and derived files to ensure a clean estimation
if [[ -f "$OUTPUT_DIR/SPM.mat" ]]; then
    echo "Removing existing model and derived files to ensure consistency..."
    rm -f "$OUTPUT_DIR"/SPM.mat
    rm -f "$OUTPUT_DIR"/beta_*.nii
    rm -f "$OUTPUT_DIR"/con_*.nii
    rm -f "$OUTPUT_DIR"/spmT_*.nii
    rm -f "$OUTPUT_DIR"/spmF_*.nii
    rm -f "$OUTPUT_DIR"/ResMS.nii
    rm -f "$OUTPUT_DIR"/mask.nii
    rm -f "$OUTPUT_DIR"/RPV.nii
    # Also clean old TFCE results and reports to avoid confusion
    rm -f "$OUTPUT_DIR"/tfce_*.nii
    rm -f "$OUTPUT_DIR"/*_log_pfwe*.nii
    rm -f "$OUTPUT_DIR"/report.html
    rm -rf "$OUTPUT_DIR"/report
    echo "✓ Cleaned old results"
fi

# Ensure logs directory exists
mkdir -p "$LOG_DIR"

# Determine estimation method
EST_METHOD="matlabbatch{1}.spm.stats.fmri_est.method.Classical = 1;"
echo "Using Classical Estimation (ReML)"

MATLAB_MODEL_LOG="$LOG_DIR/matlab_model_estimation.log"
if [[ "$USE_STANDALONE" == "true" ]]; then
    # Standalone fix: 'run' command fails on scripts in temp dirs.
    # We add the temp dir to path and call the script by name (spm_batch).
    # However, compiled MATLAB is very picky about adding paths and running scripts dynamically.
    # The most robust way is to READ the batch file content and EVAL it.
    # Note: We must ensure the file path is absolute and accessible.
    run_matlab "warning('off','MATLAB:dispatcher:nameConflict'); warning('off','all'); set(0,'DefaultFigureVisible','off'); set(0,'DefaultFigureCreateFcn',@(h,ev)[]); $UTILS_PATH_CMD spm('defaults', 'FMRI'); spm_jobman('initcfg'); fprintf('═══════════════════════════════════════════════════════\n'); fprintf('Running Factorial Design Specification\n'); fprintf('═══════════════════════════════════════════════════════\n\n'); fid=fopen('$TEMP_DIR/spm_batch.m'); if fid==-1, error('Cannot open batch file: $TEMP_DIR/spm_batch.m'); end; txt=fread(fid,'*char')'; fclose(fid); eval(txt); try, spm_jobman('run', matlabbatch); catch e, fprintf('Warning: Design reporting failed (expected in headless mode):\n%s\n', e.message); end; clear matlabbatch; fprintf('\n═══════════════════════════════════════════════════════\n'); fprintf('Running Model Estimation\n'); fprintf('═══════════════════════════════════════════════════════\n\n'); matlabbatch{1}.spm.stats.fmri_est.spmmat = {'$OUTPUT_DIR/SPM.mat'}; matlabbatch{1}.spm.stats.fmri_est.write_residuals = 0; $EST_METHOD spm_jobman('run', matlabbatch); fprintf('\n✓ Model estimation complete\n\n');" 2>&1 | tee -a "$MATLAB_MODEL_LOG" || {
        echo "Error: Model estimation failed"
        echo "Check MATLAB log: $MATLAB_MODEL_LOG"
        exit 1
    }
else
    run_matlab "warning('off','MATLAB:dispatcher:nameConflict'); warning('off','all'); set(0,'DefaultFigureVisible','off'); set(0,'DefaultFigureCreateFcn',@(h,ev)[]); $UTILS_PATH_CMD spm('defaults', 'FMRI'); spm_jobman('initcfg'); fprintf('═══════════════════════════════════════════════════════\n'); fprintf('Running Factorial Design Specification\n'); fprintf('═══════════════════════════════════════════════════════\n\n'); run('$TEMP_DIR/spm_batch.m'); try, spm_jobman('run', matlabbatch); catch e, fprintf('Warning: Design reporting failed (expected in headless mode):\n%s\n', e.message); end; clear matlabbatch; fprintf('\n═══════════════════════════════════════════════════════\n'); fprintf('Running Model Estimation\n'); fprintf('═══════════════════════════════════════════════════════\n\n'); matlabbatch{1}.spm.stats.fmri_est.spmmat = {'$OUTPUT_DIR/SPM.mat'}; matlabbatch{1}.spm.stats.fmri_est.write_residuals = 0; $EST_METHOD spm_jobman('run', matlabbatch); fprintf('\n✓ Model estimation complete\n\n');" 2>&1 | tee -a "$MATLAB_MODEL_LOG" || {
        echo "Error: Model estimation failed"
        echo "Check MATLAB log: $MATLAB_MODEL_LOG"
        exit 1
    }
fi

echo "✓ Model estimation complete"
echo ""

# Export design matrix to CSV for inspection (Priority Request)
echo "Exporting design matrix to CSV..."
run_matlab "warning('off','all'); load('$OUTPUT_DIR/SPM.mat'); X = SPM.xX.X; csvwrite('$OUTPUT_DIR/design_matrix.csv', X);" || {
    echo "Warning: Failed to export design matrix to CSV"
}
if [[ -f "$OUTPUT_DIR/design_matrix.csv" ]]; then
    echo "✓ Design matrix exported to: $OUTPUT_DIR/design_matrix.csv"
fi
echo ""

# ============================================================================
# Step 3b: Check for missing voxels across images (optional diagnostic)
# This helps detect voxels with many NaNs or missing data that can break
# permutation schemes. Writes summary JSON and an exclusion mask PNG/NIfTI.
# ============================================================================

echo "Running missing-voxel diagnostics (this is fast)"
# Read optional failure threshold from config.ini (empty disables failure)
MISSING_FAIL_PCT=$(get_ini_value "TFCE" "missing_fail_pct" "")

# Thickness is surface-based; skip volumetric missing-voxel diagnostics.
if [[ "$MODALITY" == "thickness" ]]; then
    echo "Skipping volumetric missing-voxel diagnostic for thickness modality"
else
    GM_MASK_ARG=""
    if [[ -n "$MASK_FILE" ]]; then
        GM_MASK_ARG="--gm-mask $MASK_FILE"
    fi
    if [[ -n "$MISSING_FAIL_PCT" && "$MISSING_FAIL_PCT" != "false" ]]; then
        python3 "$STATS_DIR/utils/check_missing_voxels.py" --spm "$OUTPUT_DIR/SPM.mat" --output-dir "$OUTPUT_DIR" --threshold 0.05 --fail-if-pct-excluded "$MISSING_FAIL_PCT" || {
            echo "❌ Missing-voxel fraction exceeded ${MISSING_FAIL_PCT}% — aborting pipeline."
            exit 1
        }
    else
        python3 "$STATS_DIR/utils/check_missing_voxels.py" --spm "$OUTPUT_DIR/SPM.mat" --output-dir "$OUTPUT_DIR" --threshold 0.05 $GM_MASK_ARG || {
            echo "⚠️  Warning: missing-voxel diagnostic failed (see script output above). Continuing analysis."
        }
    fi
fi

# Diagnostic: Print SPM column names to debug contrast generation
echo "Diagnostic: Checking SPM design matrix column names..."
run_matlab "warning('off','all'); load('$OUTPUT_DIR/SPM.mat'); fprintf('SPM Design Matrix Columns:\n'); for i=1:length(SPM.xX.name), fprintf('%d: %s\n', i, SPM.xX.name{i}); end;" || {
    echo "Warning: Failed to inspect SPM.mat"
}
echo ""

# ============================================================================
# Step 4: Add Contrasts
# ============================================================================

echo "┌────────────────────────────────────────────────────────────────────────┐"
echo "│ STEP 4: Adding Contrasts                                              │"
echo "└────────────────────────────────────────────────────────────────────────┘"
echo ""

# Ensure logs directory exists for this step
mkdir -p "$LOG_DIR"

MATLAB_CONTRAST_LOG="$LOG_DIR/matlab_contrasts.log"
# Remove inner try-catch so exceptions propagate to the wrapper script
# Standalone fix: Read and eval the contrast script to bypass path/function restrictions
CONTRAST_SCRIPT="$STATS_DIR/utils/add_contrasts_longitudinal.m"
run_matlab "warning('off','MATLAB:dispatcher:nameConflict'); warning('off','all'); $UTILS_PATH_CMD spm('defaults', 'FMRI'); spm_jobman('initcfg'); stats_dir='$OUTPUT_DIR'; fid=fopen('$CONTRAST_SCRIPT'); if fid==-1, error('Cannot open contrast script: $CONTRAST_SCRIPT'); end; txt=fread(fid,'*char')'; fclose(fid); txt=regexprep(txt,'^function[^\n]*\n',''); txt=regexprep(txt,'\nend\s*$',''); eval(txt);" 2>&1 | tee -a "$MATLAB_CONTRAST_LOG" || {
        echo "Error: Adding contrasts failed"
        echo "Check MATLAB log: $LOG_DIR/matlab_contrasts.log"
        if [[ -f "$LOG_DIR/matlab_contrasts.log" ]]; then
            echo ""
            echo "Last lines of MATLAB log:"
            tail -20 "$LOG_DIR/matlab_contrasts.log"
        fi
        exit 1
    }

echo "✓ Contrasts added"
echo ""

# Verify contrasts were written to disk. If none found, fail early with diagnostics.
echo "Verifying contrast files written to: $OUTPUT_DIR"
shopt -s nullglob
if [[ "$MODALITY" == "vbm" ]]; then
    cons=( "$OUTPUT_DIR"/con_*.nii )
    spmTs=( "$OUTPUT_DIR"/spmT_*.nii )
    spmFs=( "$OUTPUT_DIR"/spmF_*.nii )
else
    # Surface-based modalities (e.g. thickness) write GIfTI outputs
    cons=( "$OUTPUT_DIR"/con_*.gii )
    spmTs=( "$OUTPUT_DIR"/spmT_*.gii )
    spmFs=( "$OUTPUT_DIR"/spmF_*.gii )
fi
if [[ ${#cons[@]} -eq 0 && ${#spmTs[@]} -eq 0 && ${#spmFs[@]} -eq 0 ]]; then
    echo "ERROR: No contrast or statistic files found in $OUTPUT_DIR after adding contrasts."
    echo "Contents of results folder:";
    ls -al "$OUTPUT_DIR" || true
    echo "Check MATLAB console output above for errors during contrast creation."
    exit 1
else
    echo "Found ${#cons[@]} contrast files and ${#spmTs[@]} spmT files and ${#spmFs[@]} spmF files"
fi
shopt -u nullglob

# Generate design matrix visualization
echo "Generating design matrix image..."
run_matlab "warning('off','all'); set(0,'DefaultFigureVisible','off'); set(0,'DefaultFigureCreateFcn',@(h,ev)[]); beep off; load('$OUTPUT_DIR/SPM.mat'); imagesc(SPM.xX.X); colormap(gray); axis image; xlabel('Parameters'); ylabel('Scans'); title('Design Matrix'); saveas(gcf, '$OUTPUT_DIR/design_matrix.png');" || {
        echo "⚠️  Warning: Design matrix image generation failed"
    }

echo ""

# ============================================================================
# Step 5: Screen Contrasts
# ============================================================================

if [[ "$SKIP_SCREENING" == false ]]; then
    echo "┌────────────────────────────────────────────────────────────────────────┐"
    echo "│ STEP 5: Screening Contrasts (p<$UNCORRECTED_P uncorrected)                     │"
    echo "└────────────────────────────────────────────────────────────────────────┘"
    echo ""
    
    # Standalone fix: Read and eval screen_contrasts
    SCREEN_SCRIPT="$STATS_DIR/utils/screen_contrasts.m"
    run_matlab "warning('off','MATLAB:dispatcher:nameConflict'); warning('off','all'); set(0,'DefaultFigureVisible','off'); set(0,'DefaultFigureCreateFcn',@(h,ev)[]); $UTILS_PATH_CMD spm('defaults','FMRI'); spm_jobman('initcfg'); stats_folder='$OUTPUT_DIR'; varargin={'p_thresh',$UNCORRECTED_P,'cluster_size',$CLUSTER_SIZE}; fid=fopen('$SCREEN_SCRIPT'); if fid==-1, error('Cannot open screen script'); end; txt=fread(fid,'*char')'; fclose(fid); txt=regexprep(txt,'^function[^\n]*\n',''); txt=regexprep(txt,'\nend\s*$',''); try, eval(txt); fprintf('\\n✓ Screening complete with %d significant contrasts\\n\\n', length(significant_contrasts)); fid=fopen(fullfile('$OUTPUT_DIR','logs','significant_contrasts.txt'),'w'); if fid>0, for ii=1:numel(significant_contrasts), fprintf(fid,'%d\\n',significant_contrasts(ii)); end; fclose(fid); end; catch e, fprintf('MATLAB_ERROR:%s\\n', e.message); end;" || {
        echo "Error: Screening failed"
        exit 1
    }
    
    echo "✓ Screening complete"
    echo ""
else
    echo "┌────────────────────────────────────────────────────────────────────────┐"
    echo "│ STEP 5: Skipped (running TFCE on all contrasts)                       │"
    echo "└────────────────────────────────────────────────────────────────────────┘"
    echo ""
fi

if [[ "$NO_TFCE" == true ]]; then
    echo "┌────────────────────────────────────────────────────────────────────────┐"
    echo "│ STEP 6: Skipped (TFCE disabled by --no-tfce)                          │"
    echo "└────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo "Pipeline stopping early as requested."
    echo "Results saved to: $OUTPUT_DIR"
    exit 0
fi

# ============================================================================
# Step 6: TFCE Correction
# ============================================================================

mkdir -p "$LOG_DIR"

TFCE_LOG="$LOG_DIR/matlab_tfce.log"
TFCE_SUMMARY="$LOG_DIR/tfce_cc_summary.json"

print_tfce_summary_table() {
    local summary_path="$1"
    local threshold="$2"
    python3 - "$summary_path" "$threshold" <<'PY'
import json
import sys

summary_path = sys.argv[1]
threshold = float(sys.argv[2])
try:
    with open(summary_path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
except FileNotFoundError:
    print(f"  Summary file not found: {summary_path}")
    sys.exit(1)
except json.JSONDecodeError as exc:
    print(f"  Could not parse summary JSON ({exc})")
    sys.exit(1)

if not data:
    print("  (no contrasts recorded)")
    sys.exit(0)

print("  Contrast  Probe_cc  Recommended_full_method  Logged_full_method")
for entry in data:
    con = entry.get('contrast')
    con_str = str(con) if con is not None else '--'
    cc = entry.get('probe_cc')
    try:
        cc_val = float(cc) if cc is not None else None
    except (TypeError, ValueError):
        cc_val = None
    cc_str = f"{cc_val:.4f}" if cc_val is not None else "--"
    recommended = 'freedman-lane' if (cc_val is not None and cc_val < threshold) else 'smith'
    logged = entry.get('chosen_full_method') or '--'
    print(f"    {con_str:>4}     {cc_str:>8}  {recommended:<22} {logged:<18}")
PY
}

echo "┌────────────────────────────────────────────────────────────────────────┐"
echo "│ STEP 6: TFCE Permutation Testing                                      │"
echo "└────────────────────────────────────────────────────────────────────────┘"
echo ""

# If screening was run and produced an (empty) significant list, skip TFCE.
SKIP_TFCE=false

SIGNIF_FILE="$OUTPUT_DIR/logs/significant_contrasts.txt"
if [[ "$PILOT_MODE" != true && "$SKIP_SCREENING" == false && -f "$SIGNIF_FILE" ]]; then
    if [[ ! -s "$SIGNIF_FILE" ]]; then
        echo "No significant contrasts found by screening (file: $SIGNIF_FILE). Skipping TFCE step."
        SKIP_TFCE=true
    fi
fi

if [[ "$SKIP_TFCE" == true ]]; then
    echo "Skipping TFCE step because no screened contrasts were significant."
else
if [[ "$PILOT_MODE" == true ]]; then
    # In pilot mode run the quick TFCE directly (keep behavior simple)
    echo "Pilot mode: running single short TFCE run (${N_PERM} perms)"
    # Standalone fix: Read and eval run_tfce_correction
    TFCE_SCRIPT="$STATS_DIR/utils/run_tfce_correction.m"
    run_matlab "warning('off','MATLAB:dispatcher:nameConflict'); warning('off','all'); set(0,'DefaultFigureVisible','off'); set(0,'DefaultFigureCreateFcn',@(h,ev)[]); $UTILS_PATH_CMD spm('defaults', 'FMRI'); spm_jobman('initcfg'); fprintf('Starting pilot TFCE with %d permutations\n', $N_PERM); stats_folder='$OUTPUT_DIR'; varargin={'n_perm', $N_PERM, 'n_jobs', $N_JOBS, 'pilot', true, 'config_file', '$CONFIG_FILE'}; fid=fopen('$TFCE_SCRIPT'); if fid==-1, error('Cannot open TFCE script'); end; txt=fread(fid,'*char')'; fclose(fid); txt=regexprep(txt,'^function[^\n]*\n',''); txt=regexprep(txt,'\nend\s*$',''); eval(txt);" 2>&1 | tee -a "$TFCE_LOG" || {
        echo "Error: TFCE correction (pilot) failed"
        exit 1
    }
else
    # Standard TFCE run (single stage, no probe)
    echo "Running TFCE correction (${N_PERM} permutations)"
    
    # Convert SKIP_SCREENING (bash string) to MATLAB boolean
    if [[ "$SKIP_SCREENING" == "true" ]]; then
        USE_SCREENING="false"
    else
        USE_SCREENING="true"
    fi

    # Standalone fix: Read and eval run_tfce_correction
    TFCE_SCRIPT="$STATS_DIR/utils/run_tfce_correction.m"
    run_matlab "warning('off','MATLAB:dispatcher:nameConflict'); warning('off','all'); set(0,'DefaultFigureVisible','off'); set(0,'DefaultFigureCreateFcn',@(h,ev)[]); $UTILS_PATH_CMD spm('defaults', 'FMRI'); spm_jobman('initcfg'); fprintf('Starting TFCE with %d permutations\n', $N_PERM); stats_folder='$OUTPUT_DIR'; varargin={'n_perm', $N_PERM, 'n_jobs', $N_JOBS, 'use_screening', $USE_SCREENING, 'config_file', '$CONFIG_FILE'}; fid=fopen('$TFCE_SCRIPT'); if fid==-1, error('Cannot open TFCE script'); end; txt=fread(fid,'*char')'; fclose(fid); txt=regexprep(txt,'^function[^\n]*\n',''); txt=regexprep(txt,'\nend\s*$',''); eval(txt);" 2>&1 | tee -a "$TFCE_LOG" || {
        echo "Error: TFCE correction failed"
        exit 1
    }
fi

echo "✓ TFCE correction complete"
echo ""

# ============================================================================
# Step 6b: Generate TFCE Summary
# ============================================================================

echo "Generating TFCE results summary..."
python3 "$STATS_DIR/utils/generate_tfce_images.py" \
    --output-dir "$OUTPUT_DIR" \
    --fwe-threshold 0.05 \
    --start-time "$PIPELINE_START_TIME" || {
        echo "⚠️  Warning: TFCE summary generation failed"
    }

echo ""

# ============================================================================
# Step 7: Generate HTML Report
# ============================================================================

fi


echo "┌────────────────────────────────────────────────────────────────────────┐"
echo "│ STEP 7: Generating HTML Report                                        │"
echo "└────────────────────────────────────────────────────────────────────────┘"
echo ""

# Provide number of contrasts to the report generator (count con_*.nii)
# Provide number of contrasts to the report generator, using extension
# appropriate for modality (.nii for VBM, .gii for surface modalities).
if [[ "$MODALITY" == "vbm" ]]; then
    N_CONTRASTS=$(ls -1 "$OUTPUT_DIR"/con_*.nii 2>/dev/null | wc -l)
else
    N_CONTRASTS=$(ls -1 "$OUTPUT_DIR"/con_*.gii 2>/dev/null | wc -l)
fi

# Build a safely-quoted command-line string from the original args. Use
# printf '%q' so special characters and quotes are escaped and the result
# is safe to pass as a single argument to Python.
SAFE_CMDLINE="$(printf '%q ' "$0" "${ORIGINAL_ARGS[@]}")"

python3 "$STATS_DIR/utils/generate_html_report.py" \
    --design-json "$TEMP_DIR/design.json" \
    --output "$OUTPUT_DIR/report.html" \
    --analysis-name "$ANALYSIS_NAME" \
    --output-dir "$OUTPUT_DIR" \
    --command-line "$SAFE_CMDLINE" \
    --n-contrasts "$N_CONTRASTS" \
    --n-perm "$N_PERM" \
    --cluster-size "$CLUSTER_SIZE" \
    --uncorrected-p "$UNCORRECTED_P" \
    --start-time "$PIPELINE_START_TIME" || {
        echo "⚠️  Warning: HTML report generation failed"
    }

echo ""

# ============================================================================
# Cleanup
# ============================================================================

echo "Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

echo "Pipeline complete! Results saved to: $OUTPUT_DIR"
echo ""
