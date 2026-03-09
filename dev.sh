#!/usr/bin/env bash
# dev.sh — development helper for gemini-live-tools
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$REPO_DIR/.venv"
PYTHON="$VENV/bin/python"

# ── helpers ──────────────────────────────────────────────────────────────────

ensure_venv() {
    if [ ! -f "$PYTHON" ]; then
        echo "Creating .venv..."
        python3.10 -m venv "$VENV"
        "$VENV/bin/pip" install -e "$REPO_DIR/python"
        echo "Done."
    fi
}

cmd_setup() {
    echo "Setting up .venv..."
    python3.10 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -e "$REPO_DIR/python"
    echo "Done."
}

cmd_test() {
    ensure_venv
    echo "Running greet_demo..."
    "$PYTHON" "$REPO_DIR/python/greet_demo.py" "${@}"
}

cmd_shell() {
    ensure_venv
    echo "Activating .venv — type 'deactivate' to exit."
    exec "$VENV/bin/bash" --login
}

# ── dispatch ─────────────────────────────────────────────────────────────────

case "${1:-}" in
    --setup|setup)   shift; cmd_setup "$@" ;;
    --test|test)     shift; cmd_test "$@" ;;
    --shell|shell)   shift; cmd_shell "$@" ;;
    *)
        echo "Usage: $0 <command>"
        echo ""
        echo "  setup   Create/reinstall the .venv"
        echo "  test    Run the interactive character greeting demo"
        echo "  shell   Drop into a shell with the .venv activated"
        ;;
esac
