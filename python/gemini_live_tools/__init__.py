"""gemini-live-tools — shared Gemini Live TTS API and math evaluator."""

from pathlib import Path as _Path

_JS_DIR = _Path(__file__).resolve().parent.parent.parent / "js"


def get_static_content(filename: str) -> str:
    """Return the text content of a JS asset from the repo js/ directory."""
    if not _JS_DIR.is_dir():
        raise FileNotFoundError(f"js/ directory not found: {_JS_DIR}")
    path = (_JS_DIR / filename).resolve()
    if not path.is_relative_to(_JS_DIR):
        raise ValueError(f"filename must resolve inside js/: {filename}")
    return path.read_text(encoding="utf-8")


from .gemini_live_api import (
    GeminiLiveAPI,
    ParallelTTSStatus,
    pcm_to_wav_bytes,
    write_wav_file,
    get_character_definitions,
    get_character_default_voices,
    _split_sentences,
    MODEL_SUPPORTS_MARKUP_TAGS,
    DEFAULT_LIVE_MODEL,
    DEFAULT_PREP_MODEL,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_VOICE,
    CHARACTERS,
    CHARACTER_DEFAULT_VOICES,
)
from .math_eval import (
    safe_eval_math,
    eval_math_sweep,
    MATH_NAMES,
    HAS_NUMPY,
)

__all__ = [
    "get_static_content",
    "GeminiLiveAPI",
    "ParallelTTSStatus",
    "pcm_to_wav_bytes",
    "write_wav_file",
    "get_character_definitions",
    "get_character_default_voices",
    "MODEL_SUPPORTS_MARKUP_TAGS",
    "DEFAULT_LIVE_MODEL",
    "DEFAULT_PREP_MODEL",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_VOICE",
    "CHARACTERS",
    "CHARACTER_DEFAULT_VOICES",
    "safe_eval_math",
    "eval_math_sweep",
    "MATH_NAMES",
    "HAS_NUMPY",
]
