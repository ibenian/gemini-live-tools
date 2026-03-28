# gemini-live-tools — Agent Guidelines

## Project Overview

`gemini-live-tools` is a Python library providing:
- **Parallel TTS streaming** via Gemini Live API with voice characters
- **Safe math expression evaluator** (AST-based, numpy-backed)
- **JS widget** — drop-in voice/character picker for browser UIs

It is used as a dependency by other projects (e.g. algebench), pinned to a release tag.

## Running the Demo

```bash
./run.sh setup                                        # create .venv, install deps, symlink gstts
./run.sh gstts                                        # interactive character TTS
./run.sh gstts "Hello world"                          # read text aloud with a character voice
gstts "Hello world"                                   # same, via symlink (after setup)
./run.sh test                                         # run Python tests
./run.sh test-player                                  # open TTS audio player test page in browser
```

## Project Structure

```
run.sh                    Unified entry point (setup, test, gstts, etc.) — uses uv
python/
  gemini_live_tools/
    gemini_live_api.py     GeminiLiveAPI, character definitions, PCM/WAV helpers
    math_eval.py           Safe AST-based math evaluator
  gstts.py                 Gemini Streaming TTS CLI
  tests/                   Python tests

js/
  tts-audio-player.js      Streaming WAV/PCM audio player (Web Audio API)
  voice-character-selector.js   Drop-in voice/character picker UI widget

docs/
  streaming-tts-endpoint.md    FastAPI streaming endpoint guide with cancellation

test_tts_audio_player.html    Browser test page for TTS audio player
CONTRIBUTING.md               How to add voice characters
```

## Key Conventions

- **Never commit without explicit user instruction.** Wait for the user to say "ok commit", "commit it", or similar before running `git commit`.
- **Never create a PR without explicit user instruction.** Wait for the user to say "create PR", "open PR", or similar before running `gh pr create`.
- **Always announce who is committing before running `git commit`** — print a line in the format:
  `Committing on behalf of <name> (<email>)`
  using the output of `git config user.name` and `git config user.email`.
- **Versioning**: tag first (`v0.1.7`), then bump `pyproject.toml` to next version (`0.1.8`) and commit. See version-bump skill.
- **Release tags only** — consumers pin to a git tag. Never tell users to install from `main`.
- **`prepare_text` is called by the caller**, not inside `stream_parallel_wav` / `astream_parallel_wav`. Keep it that way.
- **Sentence boundaries**: `[long pause]` and `[medium pause]` tags split sentences in `_split_sentences`. The tag is kept at the start of the next chunk.
- **Quota awareness**: each sentence = one Gemini API request. Avoid very small `min_sentence_chars` in production (free tier is 100 req/day).
- **`.venv` is local** — recreate with `./run.sh setup` if broken.
- **Always label PRs** — add appropriate labels (e.g. `enhancement`, `bug`, `docs`) when creating PRs, same as you would for issues.
- **Use `--admin` when merging PRs** — branch protection requires it: `gh pr merge <number> --squash --delete-branch --admin`.

## Release Flow

1. Tag the current commit: `git tag vX.Y.Z && git push origin vX.Y.Z`
2. Bump `python/pyproject.toml` to next patch and commit: `chore: bump version to X.Y.Z`
3. Push

## Key API

```python
from gemini_live_tools import GeminiLiveAPI, ParallelTTSStatus

api = GeminiLiveAPI(api_key="...")

# Single-shot
prepared = api.prepare_text(text, character_name="crisp")
wav = api.synthesize_wav(prepared, character_name="crisp")

# Parallel sync streaming
for chunk in api.stream_parallel_wav(prepared, parallelism=4, character_name="crisp"):
    play(chunk)

# Parallel async streaming (FastAPI)
async for chunk in api.astream_parallel_wav(prepared, parallelism=4, character_name="crisp"):
    yield chunk
```

See [`docs/streaming-tts-endpoint.md`](docs/streaming-tts-endpoint.md) for the full FastAPI endpoint + JS client example.
