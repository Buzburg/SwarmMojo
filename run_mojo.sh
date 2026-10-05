#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if ! command -v pixi >/dev/null 2>&1; then
    echo "ROMS requires Pixi inside Linux/WSL. Install Pixi, then run pixi install in this folder." >&2
    exit 1
fi
case "${1:-}" in
    --test) exec pixi run test ;;
    "") exec pixi run server ;;
    *) echo "Usage: bash run_mojo.sh [--test]" >&2; exit 2 ;;
esac
