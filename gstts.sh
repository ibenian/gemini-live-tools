#!/usr/bin/env bash
# gstts.sh — Gemini Streaming Text-to-Speech
set -e

SCRIPT="$0"
[ -L "$SCRIPT" ] && SCRIPT="$(readlink "$SCRIPT")"
REPO_DIR="$(cd "$(dirname "$SCRIPT")" && pwd)"
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

    # Install system-wide symlink
    local link="/usr/local/bin/gstts"
    local target="$REPO_DIR/gstts.sh"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$target" ]; then
        echo "Symlink $link already points to $target"
    else
        echo "Installing symlink: $link → $target"
        ln -sf "$target" "$link"
    fi

    echo "Done."
}

cmd_run() {
    ensure_venv
    "$PYTHON" "$REPO_DIR/python/gstts.py" "${@}"
}

# ── dispatch ─────────────────────────────────────────────────────────────────

case "${1:-}" in
    --setup|setup)   shift; cmd_setup "$@" ;;
    --help|-h)
        echo "Usage: $0 [TEXT] [options]"
        echo ""
        echo "  gstts \"Hello world\"              Read text aloud with a character voice"
        echo "  gstts                             Interactive: pick character, generate greeting"
        echo "  gstts -lc                         List available characters"
        echo "  gstts -lv                         List available voices"
        echo "  gstts setup                       Create .venv and install /usr/local/bin/gstts"
        ;;
    *)  cmd_run "$@" ;;
esac
