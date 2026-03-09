#!/usr/bin/env python3
"""Interactive character greeting demo.

Usage:
    python greet_demo.py [--parallelism N]

Picks a character, generates a creative in-character greeting via Gemini,
prepares it for TTS, and plays it aloud.

  --parallelism 1   Sequential mode: single TTS call (default)
  --parallelism N   Parallel mode: split into sentences, synthesize N at a time,
                    stream and play chunks in order as they complete

Requires: GEMINI_API_KEY env var
"""

import os
import sys
import argparse
import tempfile
import subprocess

from simple_term_menu import TerminalMenu
from google import genai

from gemini_live_tools import GeminiLiveAPI, CHARACTERS


def pick_character() -> str:
    names = sorted(CHARACTERS.keys())
    entries = [
        f"{name:<22} {CHARACTERS[name].split('.')[0].split('—')[0].strip()}"
        for name in names
    ]
    menu = TerminalMenu(
        entries,
        title="Pick a character (↑↓ / PgUp PgDn / press / to search):",
        search_key="/",
        show_search_hint=True,
    )
    idx = menu.show()
    if idx is None:
        sys.exit(0)
    return names[idx]


def generate_greeting(client, character: str) -> str:
    char_desc = CHARACTERS[character]
    prompt = (
        f"You are: {char_desc}\n\n"
        "Generate a short, creative greeting (2–4 sentences) that perfectly captures "
        "your character's voice, style, and personality. Make it original and vivid. "
        "Plain text only — no markdown, no bullet points."
    )
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
    )
    return (response.text or "").strip()


def play_wav(wav_bytes: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        path = f.name
    try:
        subprocess.run(["afplay", path], check=True)
    finally:
        os.unlink(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini character greeting demo")
    parser.add_argument(
        "--parallelism", type=int, default=1,
        help="1 = sequential (default), N > 1 = parallel TTS with N threads",
    )
    parser.add_argument(
        "--min-sentence-chars", type=int, default=80,
        help="Merge sentences shorter than this (default 80)",
    )
    parser.add_argument(
        "--min-buffer-seconds", type=float, default=30.0,
        help="Seconds of audio to buffer before playback starts (default 30)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    mode = "sequential" if args.parallelism == 1 else f"parallel (x{args.parallelism})"

    character = pick_character()
    print(f"\n→ Character:  {character}")
    print(f"→ Mode:       {mode}")

    client = genai.Client(api_key=api_key)
    api = GeminiLiveAPI(api_key=api_key, client=client)

    print("\n  Generating greeting...")
    greeting = generate_greeting(client, character)
    print(f"\n  \"{greeting}\"\n")

    print("  Preparing for TTS...")
    prepared = api.prepare_text(greeting, character_name=character)
    print(f"\n  Prepared: \"{prepared}\"\n")

    print("  Synthesizing audio...\n")

    if args.parallelism == 1:
        wav = api.synthesize_wav(prepared, character_name=character)
        if not wav:
            print(f"Error: synthesis failed — {api.last_error}")
            sys.exit(1)
        print("  Playing...\n")
        play_wav(wav)
    else:
        played = 0
        for chunk in api.stream_parallel_wav(
            prepared,
            parallelism=args.parallelism,
            min_sentence_chars=args.min_sentence_chars,
            min_buffer_seconds=args.min_buffer_seconds,
            character_name=character,
        ):
            played += 1
            play_wav(chunk)
        if not played:
            print("Error: no audio chunks returned.")
            sys.exit(1)


if __name__ == "__main__":
    main()
