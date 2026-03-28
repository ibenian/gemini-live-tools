#!/usr/bin/env bash
# run.sh — unified entry point for gemini-live-tools
set -e

SCRIPT="$0"
[ -L "$SCRIPT" ] && SCRIPT="$(readlink "$SCRIPT")"
REPO_DIR="$(cd "$(dirname "$SCRIPT")" && pwd)"
VENV="$REPO_DIR/.venv"

# ── uv helpers ──────────────────────────────────────────────────────────────

ensure_uv() {
    if ! command -v uv &>/dev/null; then
        echo "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
}

ensure_venv() {
    ensure_uv
    if [ ! -d "$VENV" ]; then
        echo "Creating .venv with uv..."
        uv venv "$VENV"
    fi
}

sync_deps() {
    ensure_venv
    uv pip install -r "$REPO_DIR/python/pyproject.toml" --python "$VENV/bin/python" -q
}

run_python() {
    PYTHONPATH="$REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" "$VENV/bin/python" "$@"
}

# ── commands ────────────────────────────────────────────────────────────────

cmd_setup() {
    ensure_venv
    sync_deps

    # Install symlink for gstts
    local target="$REPO_DIR/run.sh"
    local link="/usr/local/bin/gstts"
    local user_link="$HOME/.local/bin/gstts"

    if [ -w "$(dirname "$link")" ]; then
        if [ -e "$link" ] && [ ! -L "$link" ]; then
            echo "Warning: $link exists and is not a symlink; refusing to overwrite." >&2
        elif [ -L "$link" ] && [ "$(readlink "$link")" = "$target" ]; then
            echo "Symlink $link already points to $target"
        else
            echo "Installing symlink: $link → $target"
            ln -sf "$target" "$link"
        fi
    else
        mkdir -p "$HOME/.local/bin"
        if [ -e "$user_link" ] && [ ! -L "$user_link" ]; then
            echo "Warning: $user_link exists and is not a symlink; refusing to overwrite." >&2
        elif [ -L "$user_link" ] && [ "$(readlink "$user_link")" = "$target" ]; then
            echo "Symlink $user_link already points to $target"
        else
            echo "Installing symlink: $user_link → $target"
            ln -sf "$target" "$user_link"
        fi
        case ":$PATH:" in
            *":$HOME/.local/bin:"*) ;;
            *) echo "Note: add ~/.local/bin to your PATH" ;;
        esac
    fi

    echo "Done."
}

cmd_update() {
    ensure_venv
    echo "Updating dependencies..."
    uv pip install -r "$REPO_DIR/python/pyproject.toml" --upgrade --python "$VENV/bin/python"
    echo "Done."
}

cmd_test() {
    sync_deps
    uv pip install pytest --python "$VENV/bin/python" -q
    run_python -m pytest "$REPO_DIR/python/tests/" "$@"
}

cmd_test_player() {
    local target="$REPO_DIR/test_tts_audio_player.html"
    if command -v xdg-open &>/dev/null; then
        xdg-open "$target"
    elif command -v open &>/dev/null; then
        open "$target"
    else
        echo "Could not detect a browser opener. Open manually:" >&2
        echo "  $target" >&2
        return 1
    fi
}

cmd_gstts() {
    sync_deps
    run_python "$REPO_DIR/python/gstts.py" "$@"
}

cmd_shell() {
    sync_deps
    echo "Entering .venv shell (exit to leave)"
    exec env PYTHONPATH="$REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" "$VENV/bin/python" "$@"
}

cmd_help() {
    cat <<'HELP'
Usage: run.sh <command> [args...]

Commands:
  setup          Create .venv, install deps, symlink gstts
  update         Upgrade all dependencies in .venv
  test           Run pytest in .venv (extra args passed to pytest)
  test-player    Open TTS audio player test page in browser
  gstts [args]   Run Gemini Streaming TTS CLI
  shell          Drop into .venv Python REPL
  help           Show this message

When invoked as 'gstts', defaults to the gstts command:
  gstts "Hello world"         Read text aloud
  gstts -lc                   List characters
  gstts -lv                   List voices
HELP
}

# ── dispatch ────────────────────────────────────────────────────────────────

# If invoked via gstts symlink, default to gstts command
INVOKED_AS="$(basename "$0")"
if [ "$INVOKED_AS" = "gstts" ]; then
    cmd_gstts "$@"
    exit 0
fi

case "${1:-help}" in
    setup)   shift; cmd_setup "$@" ;;
    update)  shift; cmd_update "$@" ;;
    test)    shift; cmd_test "$@" ;;
    test-player) shift; cmd_test_player "$@" ;;
    gstts)   shift; cmd_gstts "$@" ;;
    shell)   shift; cmd_shell "$@" ;;
    help|-h|--help) cmd_help ;;
    *)
        echo "Unknown command: $1 (try: run.sh help)"
        exit 1
        ;;
esac
