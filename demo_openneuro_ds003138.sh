#!/usr/bin/env bash
set -euo pipefail

# Backward-compatible wrapper.
# New entrypoint: ./run_demo_openneuro_ds003138.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[DEPRECATED] Use: ./run_demo_openneuro_ds003138.sh $*" >&2
exec "$REPO_ROOT/run_demo_openneuro_ds003138.sh" "$@"
