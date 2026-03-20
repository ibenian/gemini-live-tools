#!/usr/bin/env python3
"""Gemini Streaming Text-to-Speech (gstts).

Usage:
    python gstts.py ["text to read"] [--parallelism N]

If text is provided, picks a character voice and reads it aloud directly.
Otherwise, picks a character and generates a creative greeting via Gemini.

  --parallelism 1   Sequential mode: single TTS call (default)
  --parallelism N   Parallel mode: split into sentences, synthesize N at a time,
                    stream and play chunks in order as they complete

Requires: GEMINI_API_KEY env var
"""

import io
import json
import os
import sys
import argparse
import threading
import tty
import termios
import wave


from simple_term_menu import TerminalMenu
from google import genai

from gemini_live_tools import GeminiLiveAPI, CHARACTERS
from gemini_live_tools.gemini_live_api import CHARACTER_DEFAULT_VOICES

GEMINI_VOICES = [
    'Zephyr', 'Puck', 'Charon', 'Kore', 'Fenrir', 'Leda', 'Orus', 'Aoede',
    'Callirrhoe', 'Autonoe', 'Enceladus', 'Iapetus', 'Umbriel', 'Algieba',
    'Despina', 'Erinome', 'Algenib', 'Rasalgethi', 'Laomedeia', 'Achernar',
    'Alnilam', 'Schedar', 'Gacrux', 'Pulcherrima', 'Achird', 'Zubenelgenubi',
    'Vindemiatrix', 'Sadachbia', 'Sadaltager', 'Sulafat',
]

CONFIG_PATH = os.path.expanduser("~/gstts_config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def pick_character():
    """Pick a character interactively. Returns (name, quick_select).

    Enter = normal select, Space = quick select (save to config, skip TTS).
    """
    names = sorted(CHARACTERS.keys())
    entries = [
        f"{name:<22} {CHARACTERS[name].split('.')[0].split('—')[0].strip()}"
        for name in names
    ]
    menu = TerminalMenu(
        entries,
        title="Pick a character (Enter=select, Space=set default, /=search):",
        search_key="/",
        show_search_hint=True,
        accept_keys=("enter", " "),
    )
    idx = menu.show()
    if idx is None:
        sys.exit(0)
    quick_select = menu.chosen_accept_key == " "
    return names[idx], quick_select


def generate_greeting(client, character: str, length: int = 100) -> str:
    char_desc = CHARACTERS[character]
    prompt = (
        f"You are: {char_desc}\n\n"
        f"Generate a creative greeting of approximately {length} words that perfectly captures "
        "your character's voice, style, and personality. Make it original and vivid. "
        "Plain text only — no markdown, no bullet points."
    )
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
    )
    return (response.text or "").strip()


def watch_for_cancel(cancel_event: threading.Event) -> None:
    """Background thread: set cancel_event when user presses 'q'."""
    import select
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while not cancel_event.is_set():
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                continue
            ch = os.read(fd, 1)
            if ch.lower() == b"q":
                cancel_event.set()
                print("\n  Cancelling...")
                break
    except Exception:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def warmup_audio(sample_rate: int = 24000) -> None:
    """Prime the audio device at the target sample rate before real playback.

    macOS Core Audio reconfigures the output device when a new sample rate is
    requested, which takes ~50-200 ms.  During that window the first real chunk
    stutters or sounds elongated.  Playing a short silent buffer here forces
    Core Audio to finish the reconfiguration so the first real chunk plays
    cleanly.
    """
    import numpy as np
    import sounddevice as sd
    sd.play(np.zeros(sample_rate // 10, dtype=np.int16), samplerate=sample_rate)
    sd.wait()


def play_wav(wav_bytes: bytes, cancel_event: threading.Event = None) -> None:
    import numpy as np
    import sounddevice as sd
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        sample_rate = wf.getframerate()
    # Apply short fade-in/fade-out (10 ms) to avoid clicks at chunk boundaries.
    fade_samples = min(int(sample_rate * 0.010), len(pcm) // 4)
    if fade_samples > 0:
        fade = np.linspace(0, 1, fade_samples, dtype=np.float32)
        pcm = pcm.astype(np.float32)
        pcm[:fade_samples] *= fade
        pcm[-fade_samples:] *= fade[::-1]
        pcm = pcm.astype(np.int16)
    sd.play(pcm, samplerate=sample_rate)
    while sd.get_stream().active:
        if cancel_event and cancel_event.is_set():
            sd.stop()
            return
        sd.sleep(100)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Streaming Text-to-Speech (gstts)")
    parser.add_argument(
        "text", nargs="?", default=None,
        help="Text to read aloud (skip greeting generation)",
    )
    parser.add_argument(
        "--character", "-c", type=str, default=None,
        help="Character name (skip interactive picker)",
    )
    parser.add_argument(
        "--list-characters", "-lc", action="store_true",
        help="List available characters and exit",
    )
    parser.add_argument(
        "--voice", "-v", type=str, default=None,
        help="Gemini voice name (overrides character default voice)",
    )
    parser.add_argument(
        "--list-voices", "-lv", action="store_true",
        help="List available Gemini voices and exit",
    )
    parser.add_argument(
        "--style", "-s", type=str, default=None,
        help="Additional style instruction for TTS",
    )
    parser.add_argument(
        "--prepare", "--perform", "-p", action="store_true", default=False,
        help="Run prepare_text on input before synthesis (rewrite for speech-friendly form)",
    )
    parser.add_argument(
        "--parallelism", type=int, default=3,
        help="1 = sequential, N > 1 = parallel TTS with N threads (default 3)",
    )
    parser.add_argument(
        "--length", type=int, default=100,
        help="Approximate word count for the generated greeting (default 100)",
    )
    parser.add_argument(
        "--min-sentence-chars", type=int, default=100,
        help="Merge sentences shorter than this (default 100)",
    )
    parser.add_argument(
        "--min-buffer-seconds", type=float, default=30.0,
        help="Seconds of audio to buffer before playback starts (default 30)",
    )
    parser.add_argument(
        "--chunk-timeout", type=float, default=15.0,
        help="Stop playback if next chunk is not ready within this many seconds after previous finishes (default 15)",
    )
    parser.add_argument(
        "--min-sentence-chars-growth", type=float, default=1.2,
        help="Multiply min-sentence-chars by this factor for each successive chunk (default 1.2, 1.0 = no growth)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="If set, merge all chunks and write the complete WAV file to this path",
    )
    parser.add_argument(
        "--live", action=argparse.BooleanOptionalAction, default=True,
        help="Use Gemini Live API for synthesis (default: on, use --no-live to disable)",
    )
    parser.add_argument(
        "--stagger-delay", type=float, default=0.5,
        help="Seconds between initial parallel API calls to avoid rate limiter bursts (default 0.5)",
    )
    parser.add_argument(
        "--debug", action="store_true", default=False,
        help="Show verbose output (prepared text, mode, synthesis details)",
    )
    args = parser.parse_args()
    debug = args.debug

    # List commands — no API key needed
    if args.list_characters:
        for name in sorted(CHARACTERS.keys()):
            voice = CHARACTER_DEFAULT_VOICES.get(name, "")
            desc = CHARACTERS[name].split('.')[0].split('—')[0].strip()
            print(f"  {name:<22} voice={voice:<12} {desc}")
        sys.exit(0)

    if args.list_voices:
        for voice in GEMINI_VOICES:
            print(f"  {voice}")
        sys.exit(0)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    config = load_config()
    mode = "sequential" if args.parallelism == 1 else f"parallel (x{args.parallelism})"

    # Resolve character: --character flag > config > interactive picker
    picked_from_menu = False
    quick_select = False
    if args.character:
        character = args.character
        if character not in CHARACTERS:
            print(f"Error: unknown character \"{character}\". Use --list-characters to see options.")
            sys.exit(1)
    elif args.text and config.get("character"):
        character = config["character"]
    else:
        character, quick_select = pick_character()
        picked_from_menu = True

    voice = args.voice or CHARACTER_DEFAULT_VOICES.get(character, "Kore")
    print(f"\n→ Character:  {character}")
    print(f"→ Voice:      {voice}")

    if quick_select:
        config["character"] = character
        save_config(config)
        print(f"→ Saved as default in {CONFIG_PATH}")
        sys.exit(0)
    if args.style:
        print(f"→ Style:      {args.style}")
    if debug:
        print(f"→ Config:     {CONFIG_PATH}")
        print(f"→ Mode:       {mode}")

    client = genai.Client(api_key=api_key)
    api = GeminiLiveAPI(api_key=api_key, client=client)

    if args.text:
        if args.prepare:
            print("→ Prepare:    on (rewriting text for speech)")
            if debug:
                print("\n  Preparing for TTS...")
            prepared = api.prepare_text(args.text, character_name=character, style=args.style)
            if debug:
                print(f"\n  Prepared: \"{prepared}\"\n")
        else:
            prepared = args.text
        if debug:
            print(f"\n  \"{prepared}\"\n")
    else:
        print("\n  Generating greeting...")
        greeting = generate_greeting(client, character, length=args.length)
        print(f"\n  \"{greeting}\"\n")

        if debug:
            print("  Preparing for TTS...")
        prepared = api.prepare_text(greeting, character_name=character, style=args.style)
        if debug:
            print(f"\n  Prepared: \"{prepared}\"\n")

    # Prime the audio device now so Core Audio finishes sample-rate
    # reconfiguration before the first real chunk arrives.
    warmup_audio()

    if debug:
        print("  Synthesizing audio...  (press q to cancel)\n")
    else:
        print("  (press q to cancel)\n")

    cancel_event = threading.Event()
    watcher = threading.Thread(target=watch_for_cancel, args=(cancel_event,), daemon=True)
    watcher.start()

    if args.parallelism == 1:
        wav = api.synthesize_wav(prepared, character_name=character, voice_name=args.voice, style=args.style, use_live=args.live)
        if not wav:
            print(f"Error: synthesis failed — {api.last_error}")
            sys.exit(1)
        if args.output:
            import pathlib
            pathlib.Path(args.output).write_bytes(wav)
            print(f"  Saved to {args.output}\n")
        if not cancel_event.is_set():
            if debug:
                print("  Playing...\n")
            play_wav(wav, cancel_event)
    else:
        played = 0
        for chunk in api.stream_parallel_wav(
            prepared,
            parallelism=args.parallelism,
            min_sentence_chars=args.min_sentence_chars,
            min_sentence_chars_growth=args.min_sentence_chars_growth,
            min_buffer_seconds=args.min_buffer_seconds,
            chunk_timeout=args.chunk_timeout,
            character_name=character,
            voice_name=args.voice,
            style=args.style,
            use_live=args.live,
            stagger_delay=args.stagger_delay,
            output_path=args.output,
        ):
            if cancel_event.is_set():
                break
            played += 1
            play_wav(chunk, cancel_event)
        if not played:
            print("Error: no audio chunks returned.")
            sys.exit(1)
        if args.output and not cancel_event.is_set():
            print(f"\n  Saved to {args.output}")

    cancel_event.set()  # stop watcher if playback finished normally
    watcher.join(timeout=1)  # wait for terminal to be restored

    if picked_from_menu and character != config.get("character"):
        answer = input(f"\n  Save \"{character}\" as default character? [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            config["character"] = character
            save_config(config)
            print(f"  Saved to {CONFIG_PATH}")


if __name__ == "__main__":
    main()
    os._exit(0)  # bypass httpx/genai connection pool atexit handlers
