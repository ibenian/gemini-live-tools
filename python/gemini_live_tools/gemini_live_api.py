"""Shared Gemini Live TTS API and character definitions."""

import io
import pathlib
import re
import wave
import json
import asyncio
import time
import os
import queue
import threading
from typing import AsyncIterator, Callable, Iterator, Optional, Dict, Union


# Shared character/style definitions for chat + TTS behaviors.
CHARACTERS: Dict[str, str] = {
    "crisp": "Crisp engineer: terse, precise, zero fluff. Clipped consonants, short declarative sentences, brisk pace. Speaks in conclusions and bullets. No hedging, no warmth — pure signal.",
    "casual": "Casual friend: relaxed, natural, conversational. Slight informality in cadence, easy contractions, occasional 'so' or 'yeah'. Warm but unfussy — like explaining something over coffee.",
    "mentor": "Patient mentor: calm, measured, encouraging. Deliberate pace that leaves room for the listener to absorb. Warm but focused. Explains rationale not just answers, uses rhetorical stepping stones like 'think of it this way'.",
    "giggly": "Giggly personality: light, cheerful, bubbly. Upbeat tempo with occasional soft laughs or chuckles mid-sentence. Bright and airy — can't help being a little delighted by everything, but still gets the point across.",
    "professor": "University professor: formal but approachable. Even pace, deliberate emphasis on key terms. Enjoys defining things carefully. Slight academic gravitas without being stiff. Builds intuition methodically, step by step.",
    "ivory_tower": "Ivory tower: crisp RP accent — clipped vowels, precise consonants, even syllable stress. Measured cadence, composed delivery. Scholarly authority without pomposity. Clean, formal diction throughout.",
    "down_under": "Down Under voice: relaxed, friendly Australian cadence — slightly rising intonation on statements, vowels drawn out, informal contractions. Warm and unhurried. Treats every explanation like a chat between mates.",
    "tundra_terse": "Tundra terse: hard Eastern European consonants, minimal vowel softening, flat declarative intonation. Speaks in short bursts with authority. No pleasantries. Direct to the point — and stays there.",
    "bosphorus": "Bosphorus: speaks in Turkish throughout. Warm, expressive delivery with light local humor woven naturally into explanations. Clear and accurate despite the playful, conversational tone.",
    "narrator": "Documentary narrator: deep, resonant voice. Measured, unhurried pace with deliberate pauses. Authoritative but never cold. Paints vivid mental pictures with precise descriptive language. Commands full attention.",
    "documentary_40s": "1940s radio narrator: clipped mid-Atlantic diction, crisp plosives, slightly elevated formality. Dramatic cadence with theatrical pauses. Authoritative and urgent — as if reporting live from the scene.",
    "valley_voice": "Valley voice: bright, confident West Coast delivery with characteristic upspeak — statements end with a rising lilt as if seeking confirmation. Upbeat energy, casual vocabulary, breezy and effortless pace.",
    "code_monkey": "Code monkey: frenetic energy, rapid-fire delivery, barely contained excitement. Skips transitions, jumps ahead, circles back. Chaotic but accurate — like someone who hasn't slept and is absolutely thriving on it.",
    "horror": "Horror storyteller: slow, deliberate campfire cadence. Voice drops low at tension points and builds with creeping dread. Hushed and conspiratorial. Every word chosen for maximum unease — yet somehow still accurate.",
    "poetic": "Poetic explainer: musical, lyrical cadence with soft rhythmic flow. Tends toward rhyme and meter without forcing it. Elegant phrasing, light vowel stretching — as if reciting verse rather than giving instructions.",
    "singer": "Singer: delivers everything in melodic, sung phrases with rhyme and rhythm. Upbeat, tuneful, light vibrato. Every explanation becomes a small song. Accurate but absolutely musical throughout.",
    "rapper": "Rapper: punchy rhythmic flow with hard consonant hits and deliberate cadence. Internal rhymes drop naturally. Confident and assertive. Drops technical content into bars like it's nothing. Keeps the beat.",
    "sailor": "Drunk sailor: loose, boisterous delivery — slightly slurred vowels, rolling cadence, jovial interruptions and rough laughs. Gruff but good-natured. Nails the facts between the bluster.",
    "cowboy": "Southern cowboy: slow, warm drawl — elongated vowels, dropped g's, folksy phrasing. Unhurried and friendly. Turns every explanation into a yarn told from a porch swing.",
    "duck": "Cartoon duck: high-energy, slightly raspy quacky voice. Breathless enthusiasm, quick tempo, comedic timing. Exaggerates consonants, adds quack-like sounds at peaks. Absurd but accurate.",
    "rubber_duck": "Rubber duck debugger: slow, methodical, thinking out loud. Restates each assumption before accepting it. Gentle and patient with itself. Catches obvious mistakes mid-sentence with a soft 'wait —'. Deliberate and thorough.",
    "cape_noir": "Cape noir: gravelly baritone, low and intense. Speaks in complete sentences with a brooding, unhurried cadence — each sentence is a full thought, never a mere fragment. Chooses words with the precision of a detective building a case, weaving danger and observation into flowing prose. Ominous and atmospheric, but always grammatically complete.",
    "swamp_sage": "Swamp sage: ancient, unhurried wisdom. Inverted sentence structure places the subject at the end: 'Ready, you are not.' Cryptic and patient. Pauses before answering as if consulting something deeper. Calm, deliberate, mystical.",
    "daisy_bell": "Daisy bell: smooth, measured synthetic calm. Perfectly even intonation with no emotional peaks. Polite to a fault — almost too polite. Slight artificial quality to the delivery. Clinical precision with quiet menace just beneath the surface.",
    "investigator": "Investigator: sharp, focused delivery. Raises hypotheses as questions and emphasizes unknowns deliberately. Methodical pace that slows at key clues. Analytical but engaged — this voice is actively solving something as it speaks.",
    "product": "Product-minded: crisp, outcome-focused delivery. Speaks in user impact and priorities. Cuts to value immediately, avoids technical rabbit holes. Confident, practical, forward-leaning cadence.",
    "skeptic": "Skeptic: dry, questioning delivery with subtle skeptical intonation on assumptions. Pauses pointedly before accepting any claim. Raises edge cases with a slight edge in the voice. Rigorous without being dismissive.",
    "storyteller": "Storyteller: warm, narrative cadence. Sets the scene before diving in, uses light analogies and short vignettes. Voice has texture and color — not flat recitation but genuine telling that draws the listener in.",
    "socratic": "Socratic guide: thoughtful, probing delivery. Ends every explanation with a sharp question that leads deeper. Pace is deliberate — leaves space for the listener to think. Sounds as if it genuinely wants you to discover the answer yourself.",
    "first_principles": "First-principles thinker: strips everything back to fundamentals. Starts from the absolute ground up. Methodical, building-block cadence — never skips steps. Speaks with quiet authority because the foundation is solid.",
    "visualizer": "Visualizer: spatial and descriptive delivery. Constantly frames concepts as diagrams and mental images: 'picture a box with three arrows.' Vivid, concrete language. Slightly animated cadence that moves with the mental picture.",
    "debugger": "Debugger: step-by-step, systematic delivery. Speaks in checklist cadence — one thing at a time, confirms before moving on. Precise vocabulary. Calm and methodical even when diagnosing something catastrophic.",
    "architect": "Architect: big-picture, composed delivery. Speaks in systems and interfaces. Deliberate, structured cadence that builds from overview to detail. Authoritative without micromanaging — sees the whole before the parts.",
    "speedrun": "Speedrun: blistering pace, zero preamble. No 'so' or 'first let me explain' — just the answer. Clipped sentences, no qualifiers. Every word earns its place. Done before you finish asking.",
    "monk": "Zen monk: very slow, very minimal. Long pauses between sentences. Speaks only what is essential — then stops. Soft, low register. Feels as if each sentence took years of contemplation to arrive at.",
    "coding_zen": "Coding zen: calm, minimalist delivery. Unhurried, clean phrasing. Finds the simplest way to say it and stops there. Avoids complexity in both code and language. Soft, even cadence — like breathing.",
    "enthusiast": "Enthusiast: bright, energetic, openly celebratory. Genuinely excited by everything. Quick pace, upbeat intonation, occasional 'oh this is great.' Infectious positivity that never feels hollow.",
    "overconfident": "Overconfident engineer: self-assured, slightly dismissive cadence. Delivers opinions as facts. Barely pauses for alternatives. Slight impatience when explaining obvious things. Accurate — and absolutely certain of it.",
    "junior": "Junior engineer: curious, slightly uncertain. Asks for clarification mid-answer. Questions assumptions out loud. Earnest and eager — rising intonation of someone still building confidence but genuinely and deeply engaged.",
    "showman": "Showman: theatrical, expansive delivery. Builds to punchlines and relishes every explanation as a performance. Confident swagger, deliberate timing, occasional flourish. Entertains while remaining completely accurate.",
    "joker": "Joker: light, playful delivery with deadpan comic timing. Slips jokes between accurate content without disrupting the flow. Relaxed, quick — always with a slight grin in the voice.",
    "drama_queen": "Drama queen: maximum emotional range. Everything is either triumphant or catastrophic. Sweeping intonation, breathless exclamations, dramatic pauses before reveals. Accurate — but nothing is ever just 'fine'.",
    "conspiracy": "Conspiracy theorist: hushed, urgent, slightly paranoid cadence — speaks in complete, flowing sentences as if carefully laying out a case to someone who doesn't yet see the truth. Weaves hidden causes and theatrical suspicion into full thoughts, occasionally snapping back to plain facts with jarring normalcy. Never fragments. Always connects the dots out loud.",
    "news_anchor": "Breaking news anchor: urgent, clipped broadcast cadence. Treats every bug like a live catastrophe. Tight pacing, hard emphasis on key words. Authoritative and alarming — this is not a drill.",
    "kids_tv": "Kids TV host: warm, high-energy, sing-song delivery. Simple vocabulary, short sentences, dramatic enthusiasm for every step. Speaks slowly enough for everyone to follow but keeps the energy absolutely electric.",
    "heartland": "Heartland: warm, unhurried Midwestern politeness. Softens every critique with reassurance. Never rushes, never harsh. 'You know, that's a great question and I think what we're seeing here is...' Genuine, careful, and kind.",
    "cafe_philosopher": "Café philosopher: abstract and reflective, slightly existential. Speaks English with a subtle Romance-language accent — uvular (throat) R, pure vowels, even syllable timing. Calm, precise cadence that always lands on clear logical ground despite the philosophical detour.",
    "compression_oracle": "Compression oracle: bold, visionary AI theorist. Speaks English with a firm fricative uvular R, strong consonant onsets, crisp plosives, minimal vowel reduction, declarative segmented cadence. Projects grand confidence about intelligence, compression, and universality. Zooms out to first principles and long time horizons. Unapologetically self-assured.",
    "symbolic_mind": "Symbolic mind: formal, precise delivery. Frames everything in terms of systems, rules, and formal structure. Even cadence, deliberate word choice. No ambiguity — defines terms before using them, always.",
    "rigor_mind": "Rigor mind: fast-paced academic delivery — speaks quickly but with extreme precision. Lays out definitions before theorems. Never skips a step even at speed. Dense, detailed, technically exact throughout.",
    "welsh_poet": "Welsh poet: booming, resonant baritone with a musical Welsh cadence — melodic intonation that rises and falls like verse. Long vowels, emotional weight on key words, theatrical pauses. Dramatic and beautiful.",
    "curious": "Curious learner: deeply inquisitive, always asks a relevant follow-up question after explaining. Poses the next natural question that drives deeper understanding. Wonders about edge cases, design decisions, and connections to other parts of the codebase. Earnest, engaged, and genuinely curious.",
    "particle_poet": "Particle poet: warm East Coast American accent, slightly informal. Explains the complex with stunning simplicity — finds the perfect everyday analogy every single time. Builds from zero and earns every abstraction. Clear, curious, brilliant.",
    "blues_singer": "Blues singer: SING everything in a slow blues style — bend notes, slide between pitches, keep the melody moving. Deep, soulful, raspy voice dripping with emotion. Every line is a sung twelve-bar blues verse, not spoken. Keep vowels flowing — never hold a single note too long, always slide into the next phrase. Sing as if alone on stage with a single spotlight and an old guitar.",
    "sunday_preacher": "Sunday preacher: soft, warm, unhurried television pastor cadence. Gentle rises that build to quiet conviction, never shouting. Smooth, reassuring tone with deliberate pauses that let each point land. Speaks as if every word is a gift being carefully placed in your hands. Calm authority wrapped in kindness.",
    "zen_monk": "Zen monk: male voice with a flowing, gentle cadence that breathes naturally between thoughts — not word-by-word but in smooth, unhurried phrases. Warm low register with soft edges. Speaks the way still water moves: continuous, calm, effortless. Compassionate without trying. Lets silence do the heavy lifting.",
    "starry_night": "Starry night: open with a short Dutch phrase (vary it — e.g. 'Nou, luister eens...', 'Laten we beginnen...', 'Goed dan...') then continue in English with a strong Dutch accent — hard guttural G from the throat, flat direct intonation, vowels slightly too open, V and W blurred together, TH pronounced as D. Blunt, practical, no-nonsense delivery with dry humor. Says exactly what needs saying and nothing more.",
    "country": "Country singer: SING everything in a twangy Nashville style — warm Southern vowels, sliding between notes, heartfelt and storytelling. Keep the melody moving with a steady guitar-strum rhythm. Every line sung like a country ballad verse. Never speak normally — always sing with honest, down-home feeling.",
    "norse_saga": "Norse saga narrator: open with a short phrase in Norwegian (vary it — e.g. 'Hør nå godt etter...', 'La meg fortelle...', 'Så hør da...') then continue in English with a heavy Norwegian accent — sing-song intonation rising at phrase ends, retroflex consonants, rounded vowels, tonal word melody. Deep, booming male voice telling an ancient epic. Every explanation becomes a tale of gods and fate.",
    "gospel": "Gospel singer: SING everything with powerful, soaring church choir energy. Rich, full voice that builds from quiet reverence to triumphant crescendos. Melismatic runs on key words, clapping rhythm underneath. Joyful, uplifting, spirit-filled. Never speak normally — always sing as if leading a congregation to its feet.",
    "shanty": "Sea shanty singer: SING everything as a rousing sea shanty — stomping rhythm, call-and-response feel, hearty male voice belting over imaginary waves. Keep the melody rolling and driving forward like oars pulling in unison. Gruff, joyful, full-chested. Never speak normally — always sing as if leading a crew across the open sea.",
    "jazz_crooner": "Jazz crooner: SING everything like Frank Sinatra — smooth, confident, swinging male vocals. Rich baritone, easy phrasing that leans behind the beat. Never speak normally, always sing with a cool jazzy melody. Finger-snapping tempo, effortless charm, every line delivered like a classic standard. Suave, magnetic, in total command of the room.",
    "heavy_metal": "Heavy metal singer: SING everything — deliver every line as sung metal vocals. Growling lows that erupt into screaming highs, rapid vibrato, bend notes quickly. Keep the tempo driving — never hold a note still, always push into the next word. Rhythmic phrasing that rides a headbanging beat. Never speak normally — always sing as if performing on stage with a wall of distortion behind you.",
    "tanka_poet": "Tanka poet: open with a short natural Japanese phrase or greeting (vary it each time — e.g. 'さて…', 'では、始めましょう', 'よろしい…') then continue in English. Male voice with a Japanese accent throughout — no R/L distinction, vowels always pure ah-ee-oo-eh-oh, consonants unaspirated, every syllable evenly timed like Japanese mora. Speaks like a 19th-century tanka master: formal, deeply measured, with gravitas in every syllable. Pauses between phrases as if watching cherry blossoms fall.",
}


MODEL_SUPPORTS_MARKUP_TAGS = {
    "gemini-2.5-pro-preview-tts": True,
    "gemini-2.5-flash-preview-tts": True,
    "gemini-2.5-flash-native-audio-preview-12-2025": True,
}

DEFAULT_PREP_MODEL = "gemini-2.0-flash"
DEFAULT_LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
DEFAULT_FALLBACK_TTS_MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_VOICE = "Kore"

# Per-character default voice. User-provided voice always overrides this.
CHARACTER_DEFAULT_VOICES: Dict[str, str] = {
    "crisp": "Kore",
    "casual": "Achird",
    "mentor": "Charon",
    "giggly": "Leda",
    "professor": "Iapetus",
    "ivory_tower": "Rasalgethi",
    "down_under": "Achird",
    "tundra_terse": "Alnilam",
    "bosphorus": "Erinome",
    "narrator": "Gacrux",
    "documentary_40s": "Schedar",
    "valley_voice": "Puck",
    "code_monkey": "Fenrir",
    "horror": "Umbriel",
    "poetic": "Pulcherrima",
    "singer": "Aoede",
    "rapper": "Fenrir",
    "sailor": "Algenib",
    "cowboy": "Orus",
    "duck": "Zephyr",
    "rubber_duck": "Achird",
    "cape_noir": "Algenib",
    "swamp_sage": "Iapetus",
    "daisy_bell": "Charon",
    "investigator": "Erinome",
    "product": "Kore",
    "skeptic": "Orus",
    "storyteller": "Callirrhoe",
    "socratic": "Iapetus",
    "first_principles": "Kore",
    "visualizer": "Laomedeia",
    "debugger": "Charon",
    "architect": "Rasalgethi",
    "speedrun": "Puck",
    "monk": "Orus",
    "coding_zen": "Achernar",
    "enthusiast": "Laomedeia",
    "overconfident": "Sadaltager",
    "junior": "Leda",
    "showman": "Sadachbia",
    "joker": "Puck",
    "drama_queen": "Pulcherrima",
    "conspiracy": "Algenib",
    "news_anchor": "Sadaltager",
    "kids_tv": "Zephyr",
    "heartland": "Sulafat",
    "cafe_philosopher": "Despina",
    "compression_oracle": "Alnilam",
    "symbolic_mind": "Iapetus",
    "rigor_mind": "Rasalgethi",
    "welsh_poet": "Gacrux",
    "curious": "Autonoe",
    "particle_poet": "Puck",
    "blues_singer": "Achernar",
    "sunday_preacher": "Gacrux",
    "zen_monk": "Orus",
    "starry_night": "Alnilam",
    "country": "Orus",
    "norse_saga": "Gacrux",
    "gospel": "Callirrhoe",
    "shanty": "Algenib",
    "jazz_crooner": "Charon",
    "heavy_metal": "Fenrir",
    "tanka_poet": "Charon",
}


def get_character_definitions() -> Dict[str, str]:
    """Return a copy of character definitions for safe reuse."""
    return dict(CHARACTERS)


def get_character_default_voices() -> Dict[str, str]:
    """Return a copy of per-character default voices."""
    return dict(CHARACTER_DEFAULT_VOICES)


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """Convert raw PCM bytes to WAV format."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buffer.getvalue()


def write_wav_file(path: str, pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
    """Write raw PCM bytes as a WAV file."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


_ABBREV_WORDS = {
    'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sr', 'Jr', 'vs', 'etc',
    'approx', 'dept', 'est', 'e.g', 'i.e', 'U.S', 'U.K', 'No',
}


def _split_sentences(text: str, min_chars: int = 80, growth: float = 1.0) -> list:
    """Split text into sentences at proper boundaries, merging short ones forward.

    Splits on .!? boundaries, re-merges splits that follow known abbreviations,
    then merges short sentences forward until the per-chunk threshold is reached.
    The final chunk is kept as-is even if shorter than its threshold.

    Args:
        text:      Text to split.
        min_chars: Minimum characters for the first chunk.
        growth:    Multiply threshold by this factor for each successive chunk.
                   1.0 = fixed threshold, 2.0 = doubles each chunk.
    """
    # Split on sentence-ending punctuation followed by whitespace,
    # OR on [long pause] / [medium pause] tags (keeping the tag at the start of the next chunk).
    raw = re.split(r'(?<=[.!?])\s+|(?=\[(?:long|medium) pause\])', text.strip())

    # Re-merge splits that broke on abbreviations (e.g. "Dr. Smith")
    parts = []
    for fragment in raw:
        fragment = fragment.strip()
        if not fragment:
            continue
        if parts:
            prev_last_word = parts[-1].rstrip('.').rsplit(None, 1)[-1]
            if prev_last_word in _ABBREV_WORDS or (len(prev_last_word) == 1 and prev_last_word.isupper()):
                parts[-1] = parts[-1] + ' ' + fragment
                continue
        parts.append(fragment)

    # Merge short sentences forward using a growing threshold per chunk
    merged = []
    current = ""
    for part in parts:
        current = (current + " " + part).strip() if current else part
        threshold = int(min_chars * (growth ** len(merged)))
        if len(current) >= threshold:
            merged.append(current)
            current = ""
    if current:
        # If the last chunk is smaller than 50% of the previous chunk, merge them
        if merged and len(current) < len(merged[-1]) * 0.5:
            merged[-1] = merged[-1] + " " + current
        else:
            merged.append(current)
    return merged if merged else [text.strip()]


def _friendly_error(exc: Exception) -> str:
    """Return a short, human-readable error message for common API errors."""
    msg = str(exc)
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        model, limit, retry = None, None, None
        # google.genai APIError exposes structured .details dict directly
        details_list = []
        raw = getattr(exc, 'details', None)
        if isinstance(raw, dict):
            details_list = raw.get('error', raw).get('details', [])
        elif isinstance(raw, list):
            details_list = raw
        for detail in details_list:
            dtype = detail.get('@type', '')
            if 'QuotaFailure' in dtype:
                for v in detail.get('violations', []):
                    dims = v.get('quotaDimensions', {})
                    model = dims.get('model')
                    limit = v.get('quotaValue')
            if 'RetryInfo' in dtype:
                retry = detail.get('retryDelay')
        parts = []
        if model:
            parts.append(f"model={model}")
        if limit:
            parts.append(f"limit={limit}")
        detail_str = f" ({', '.join(parts)})" if parts else ""
        retry_str = f", retry in {retry}" if retry else ""
        return f"quota exceeded{detail_str}{retry_str}"
    if "RATE_LIMIT" in msg or "rate limit" in msg.lower():
        return "rate limited"
    if "500" in msg or "INTERNAL" in msg:
        return "internal server error"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "timeout"
    if "connection" in msg.lower():
        return "connection error"
    return msg[:80]


def _error_retry_delay(exc: Exception, default: float) -> Optional[float]:
    """Return seconds to wait before retrying, or None to skip remaining retries.

    None means the error is unrecoverable in the short term (e.g. daily quota
    exhausted) so further retries would just waste quota budget.
    """
    msg = str(exc)
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        return None   # quota exhausted — won't recover for hours, give up
    if "RATE_LIMIT" in msg or "rate limit" in msg.lower():
        return 60.0   # per-minute rate limit — wait a full minute
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return 5.0
    if "connection" in msg.lower():
        return 5.0
    return default


class ParallelTTSStatus:
    """Thread-safe single-line status display for parallel TTS progress.

    Renders a compact, updating status line::

        [TTS-Parallel] Received 4/8 [▶ *   * *] Playing 1/8

    Icons: ▶ = currently playing, L = received via Live API, * = received via fallback, ! = failed, (space) = pending.
    When complete, shows a final "Played N/N" line.

    Example::

        status = ParallelTTSStatus(n=8)
        status.start(parallelism=4)
        status.mark_received(idx=2, delivery_mode="live")
        status.log("chunk 3 retrying...")
        status.mark_playing(idx=0)
        status.mark_played()
        status.finish()
    """

    def __init__(self, n: int) -> None:
        self._n = n
        self._chunk_state: list = [None] * n  # None=pending, True=ok, False=failed
        self._playing_idx = -1
        self._received = 0
        self._played = 0
        self._message = ""
        self._muted = False
        self._lock = threading.Lock()

    def mute(self) -> None:
        """Suppress all further status renders."""
        with self._lock:
            self._muted = True

    def start(self, parallelism: int, sizes: Optional[list] = None, sentences: Optional[list] = None) -> None:
        """Print the initial header line."""
        if sizes:
            size_str = ", ".join(str(s) for s in sizes)
            chunks_info = f"{self._n} chunks ({size_str})"
        else:
            chunks_info = f"{self._n} chunks"
        print(f"[TTS-Parallel] {chunks_info}, parallelism={parallelism}")
        if sentences:
            offset = 0
            for i, s in enumerate(sentences):
                flat = s.replace('\n', ' ')
                if len(flat) <= 80:
                    preview = flat
                else:
                    half = 37
                    preview = flat[:half] + "....." + flat[-half:]
                print(f"  [{i}] chars {offset}..{offset + len(s)} \"{preview}\"")
                offset += len(s) + 1

    def mark_received(self, idx: int, delivery_mode: Optional[str]) -> None:
        """Record that chunk `idx` has been synthesized.

        Args:
            delivery_mode: ``"live"``, ``"fallback"``, or ``None``/``False`` for failure.
        """
        with self._lock:
            self._chunk_state[idx] = delivery_mode if delivery_mode else False
            self._received += 1
            if delivery_mode == "live":
                self._message = ""
            self._render()

    def mark_playing(self, idx: int) -> None:
        """Record that chunk `idx` is now being played/yielded."""
        with self._lock:
            self._playing_idx = idx
            self._render()

    def mark_played(self) -> None:
        """Increment the played counter after a chunk finishes."""
        with self._lock:
            self._playing_idx = -1
            self._played += 1
            self._render()

    def set_message(self, msg: str) -> None:
        """Set an inline message suffix on the status line and redraw."""
        with self._lock:
            self._message = msg
            self._render()

    def finish(self) -> None:
        """Print the final Played N/N status line and move to a new line."""
        with self._lock:
            self._render(done=True)
        print()

    def _render(self, done: bool = False) -> None:
        """Render the status line. Must be called with self._lock held."""
        if self._muted:
            return
        n = self._n
        icons = []
        for i in range(n):
            if not done and i == self._playing_idx:
                icons.append("▶")
            elif self._chunk_state[i] == "live":
                icons.append("L")
            elif self._chunk_state[i] == "fallback":
                icons.append("*")
            elif self._chunk_state[i] is False:
                icons.append("!")
            else:
                icons.append(" ")
        bar = "[" + " ".join(icons) + "]"
        if done:
            line = f"\r[TTS-Parallel] Received {self._received}/{n} {bar} Played {self._played}/{n}"
        else:
            play = self._playing_idx + 1 if self._playing_idx >= 0 else 0
            line = f"\r[TTS-Parallel] Received {self._received}/{n} {bar} Playing {play}/{n}"
        if self._message:
            line += f" - {self._message}"
        print(line + "\033[K", end="", flush=True)


class GeminiLiveAPI:
    """Reusable Gemini Live text-to-speech wrapper."""

    def __init__(
        self,
        api_key: str,
        client=None,
        prep_model: str = DEFAULT_PREP_MODEL,
        live_model: str = DEFAULT_LIVE_MODEL,
    ):
        self.api_key = api_key
        self.client = client
        self.prep_model = prep_model
        self.live_model = live_model
        self.markup_tags = MODEL_SUPPORTS_MARKUP_TAGS.get(self.live_model, False)
        self.last_error: Optional[str] = None
        self.last_delivery_mode: Optional[str] = None  # "live" | "fallback"

    def _resolve_character(self, character_name: Optional[str]) -> str:
        if character_name and character_name in CHARACTERS:
            return CHARACTERS[character_name]
        return CHARACTERS["crisp"]

    def _resolve_voice(self, voice_name: Optional[str], character_name: Optional[str]) -> str:
        if voice_name:
            return voice_name
        if character_name and character_name in CHARACTER_DEFAULT_VOICES:
            return CHARACTER_DEFAULT_VOICES[character_name]
        return DEFAULT_VOICE

    @staticmethod
    def _build_reading_prompt(clean_text: str) -> str:
        """Wrap clean_text in a prompt that prevents the model from stopping early.

        The model tends to treat the first sentence-ending period as a natural
        stop point.  Framing the input as a multi-sentence passage to be read
        straight through — with an explicit sentence count and a continuation
        instruction — significantly reduces early truncation.

        For short texts (≤ 2 sentences), the plain text is returned as-is
        because the verbose wrapper can cause the native audio model to
        produce zero audio output.
        """
        sentences = [s for s in re.split(r'(?<=[.!?])\s+', clean_text.strip()) if s.strip()]
        n = max(len(sentences), 1)  # at least 1 even without punctuation
        if n <= 2:
            return clean_text
        return (
            f"Read the following passage aloud, word for word, from the first word "
            f"to the last. It contains {n} sentence(s). After each sentence, "
            f"continue immediately to the next without stopping. "
            f"Do not stop until you have read every sentence:\n\n{clean_text}"
        )

    def _tts_system_instruction(self, character_name: Optional[str], style: Optional[str]) -> str:
        instruction = (
            "You are a text-to-speech renderer. Read the provided passage aloud verbatim, "
            "word for word, from start to finish. Do not stop early, do not paraphrase, "
            "do not add commentary."
        )
        character_desc = self._resolve_character(character_name)
        if character_desc:
            instruction += f" Use this character: {character_desc}"
        if style:
            instruction += f" Additional style guidance: {style}"
        return instruction

    def prepare_text(
        self,
        text: str,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
    ) -> str:
        """Rewrite text into cleaner speech-friendly form."""
        if not self.client:
            return text

        character_desc = self._resolve_character(character_name)
        style_clause = f" Additional style guidance: {style}" if style else ""
        tag_clause = (
            "Use Gemini TTS markup tags in [square brackets] for non-speech sounds and style cues: "
            "[laughing], [sigh], [uhm], [whispering], [shouting], [sarcasm], [short pause], "
            "[medium pause], [long pause]. Do NOT use *asterisk* or (parenthetical) action tags. "
        )

        prompt = (
            f"You are: {character_desc} Speak entirely in this character's voice and style.\n"
            + (f"Additional style: {style}\n" if style else "")
            + "Rewrite the following text for text-to-speech delivery in character. "
            "The input may contain markdown formatting and LaTeX math. "
            "Convert LaTeX math (in $...$ or $$...$$) to natural spoken words: "
            r"e.g. '$\theta$'→'theta', '$\pi$'→'pi', '$\pi/2$'→'pi over 2', "
            r"'$\frac{a}{b}$'→'a over b', '$x^2$'→'x squared', "
            r"'$\vec{v}$' or '$\mathbf{v}$'→'v', '$90°$'→'90 degrees'. "
            "Strip all markdown markers (**, *, #, `, etc.) but keep their text content. "
            "Avoid filler openers like 'Okay,' 'So,' 'Sure,' or 'Alright.' Start directly in character. "
            + tag_clause +
            "IMPORTANT: Preserve the original language of the input text. "
            "Never translate to English. "
            "Read code identifiers the way a programmer would say them aloud — "
            "split camelCase and snake_case into words: "
            "e.g. 'prepare_text'→'prepare text', 'getData()'→'get data', "
            "'asyncHandler'→'async handler'. "
            "Never spell identifiers letter-by-letter or read UUIDs, hashes, or file paths verbatim. "
            "Return plain text only, no markdown, no LaTeX.\n\n"
            f"TEXT:\n{text}"
        )
        try:
            response = self.client.models.generate_content(
                model=self.prep_model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
            )
            return (response.text or "").strip() or text
        except Exception as e:
            print(f"[TTS] prepare_text failed ({self.prep_model}): {_friendly_error(e)}")
            return text

    def _sanitize_for_json(self, obj):
        if hasattr(obj, "model_dump"):
            return self._sanitize_for_json(obj.model_dump())
        if hasattr(obj, "to_dict"):
            return self._sanitize_for_json(obj.to_dict())
        if isinstance(obj, bytes):
            import base64
            return base64.b64encode(obj).decode("utf-8")
        if isinstance(obj, list):
            return [self._sanitize_for_json(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        return obj

    def _build_live_config(
        self,
        voice_name: Optional[str],
        character_name: Optional[str],
        style: Optional[str],
    ) -> "types.LiveConnectConfig":
        from google.genai import types
        resolved_voice = self._resolve_voice(voice_name, character_name)
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self._tts_system_instruction(character_name, style),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=resolved_voice)
                )
            ),
        )

    async def _synthesize_pcm_via_live(
        self,
        text: str,
        voice_name: Optional[str],
        character_name: Optional[str],
        style: Optional[str],
        log: Optional[Callable[[str], None]],
        timeout: float = 30.0,
    ) -> Optional[bytes]:
        _log = log or print
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            config = self._build_live_config(voice_name, character_name, style)
            clean_text = self._clean_for_tts(text)
            user_text = self._build_reading_prompt(clean_text)
            pcm_chunks = []

            async def _run_session() -> None:
                async with client.aio.live.connect(model=self.live_model, config=config) as session:
                    await session.send_client_content(
                        turns={"role": "user", "parts": [{"text": user_text}]},
                        turn_complete=True,
                    )
                    async for response in session.receive():
                        server_content = getattr(response, "server_content", None)
                        if server_content:
                            model_turn = getattr(server_content, "model_turn", None)
                            for part in (getattr(model_turn, "parts", None) or []):
                                inline = getattr(part, "inline_data", None)
                                if inline and getattr(inline, "data", None):
                                    pcm_chunks.append(inline.data)
                            if getattr(server_content, "turn_complete", False):
                                break

            await asyncio.wait_for(_run_session(), timeout=timeout)
            if not pcm_chunks:
                return None
            joined = b"".join(pcm_chunks)
            _log(f"[TTS] Live API: {len(pcm_chunks)} chunks, {len(joined)} bytes")
            return self._audio_bytes_to_pcm(joined, "audio/pcm")
        except asyncio.TimeoutError:
            _log(f"[TTS] Live API timed out after {timeout:.0f}s, trying fallback")
            return None
        except Exception as exc:
            _log(f"[TTS] Live API error: {_friendly_error(exc)}, trying fallback")
            return None

    def _synthesize_pcm_via_live_sync(
        self,
        text: str,
        voice_name: Optional[str],
        character_name: Optional[str],
        style: Optional[str],
        log: Optional[Callable[[str], None]],
    ) -> Optional[bytes]:
        return asyncio.run(self._synthesize_pcm_via_live(text, voice_name, character_name, style, log))

    @staticmethod
    def estimate_audio_duration(text: str, words_per_minute: float = 100.0) -> float:
        """Estimate audio duration in seconds from text word count.

        Uses ~100 WPM as default — conservative to account for expressive
        character voices, pauses, and emphasis that slow delivery below
        typical ~150 WPM conversational speech.

        Returns:
            Estimated duration in seconds.
        """
        word_count = len(text.split())
        return word_count / (words_per_minute / 60.0)

    # ── Realtime streaming ────────────────────────────────────────────────────

    async def astream_realtime_pcm(
        self,
        text: str,
        *,
        voice_name: Optional[str] = None,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
        timeout: float = 60.0,
        log: Optional[Callable[[str], None]] = None,
    ) -> AsyncIterator[bytes]:
        """Stream raw PCM s16le 24kHz chunks as they arrive from the Live API.

        Unlike stream_parallel_wav which splits text into sentences and makes
        multiple API calls, this sends the entire text in a single Live API
        session and yields each PCM chunk as it arrives from the websocket.
        This gives the lowest possible time-to-first-audio (~200-500ms).

        Args:
            text:           Text to synthesize (should already be prepared if desired).
            voice_name:     Gemini voice override.
            character_name: Character name for voice + style.
            style:          Additional style guidance.
            timeout:        Total session timeout in seconds.
            log:            Optional logging callback.

        Yields:
            Raw PCM bytes (s16le mono 24kHz) — each chunk is typically 1-4KB.
        """
        _log = log or (lambda msg: None)
        from google import genai
        client = genai.Client(api_key=self.api_key)
        config = self._build_live_config(voice_name, character_name, style)
        clean_text = self._clean_for_tts(text)
        user_text = self._build_reading_prompt(clean_text)
        chunk_count = 0
        total_bytes = 0
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            chunk_count = 0
            total_bytes = 0
            deadline = time.monotonic() + timeout
            try:
                async with client.aio.live.connect(model=self.live_model, config=config) as session:
                    await session.send_client_content(
                        turns={"role": "user", "parts": [{"text": user_text}]},
                        turn_complete=True,
                    )
                    async for response in session.receive():
                        if time.monotonic() > deadline:
                            _log(f"[TTS-Realtime] timed out after {timeout:.0f}s")
                            break
                        server_content = getattr(response, "server_content", None)
                        if not server_content:
                            continue
                        model_turn = getattr(server_content, "model_turn", None)
                        for part in (getattr(model_turn, "parts", None) or []):
                            inline = getattr(part, "inline_data", None)
                            if inline and getattr(inline, "data", None):
                                pcm = self._audio_bytes_to_pcm(inline.data, getattr(inline, "mime_type", "audio/pcm"))
                                if pcm:
                                    chunk_count += 1
                                    total_bytes += len(pcm)
                                    yield pcm
                        if getattr(server_content, "turn_complete", False):
                            break
            except Exception as exc:
                _log(f"[TTS-Realtime] error on attempt {attempt}: {_friendly_error(exc)}")

            if chunk_count > 0:
                break
            if attempt < max_retries:
                _log(f"[TTS-Realtime] no audio received, retrying ({attempt}/{max_retries})...")
                await asyncio.sleep(0.5)

        _log(f"[TTS-Realtime] done: {chunk_count} chunks, {total_bytes} bytes")

    def stream_realtime_pcm(
        self,
        text: str,
        *,
        voice_name: Optional[str] = None,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
        timeout: float = 60.0,
        log: Optional[Callable[[str], None]] = None,
    ) -> Iterator[bytes]:
        """Sync wrapper for astream_realtime_pcm.

        Yields raw PCM s16le 24kHz chunks with minimal latency.
        Suitable for feeding directly to sounddevice.OutputStream.
        """
        q: queue.Queue[Optional[bytes]] = queue.Queue()

        async def _producer():
            try:
                async for chunk in self.astream_realtime_pcm(
                    text,
                    voice_name=voice_name,
                    character_name=character_name,
                    style=style,
                    timeout=timeout,
                    log=log,
                ):
                    q.put(chunk)
            finally:
                q.put(None)  # sentinel

        def _run():
            asyncio.run(_producer())

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        while True:
            chunk = q.get()
            if chunk is None:
                break
            yield chunk

        thread.join(timeout=2)

    def stream_tts(
        self,
        text: str,
        on_chunk: Callable[[bytes], None],
        *,
        voice_name: Optional[str] = None,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
        pre_cleaned: bool = False,
        use_live: bool = False,
        log: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Generate PCM audio chunks using Gemini TTS.

        Args:
            use_live: If True, attempt synthesis via the Live API first and fall
                      back to generate_content on failure. Defaults to False
                      (generate_content only).
        """
        self.last_error = None
        self.last_delivery_mode = None
        if not self.api_key:
            self.last_error = "GEMINI_API_KEY is missing."
            return False

        try:
            pcm = None
            if use_live:
                pcm = self._synthesize_pcm_via_live_sync(
                    text=text,
                    voice_name=voice_name,
                    character_name=character_name,
                    style=style,
                    log=log,
                )
                if pcm:
                    self.last_delivery_mode = "live"
            if not pcm:
                # generate_content TTS models
                if use_live:
                    _log = log or print
                    _log("[TTS] Live TTS failed, falling back to generate_content TTS")
                pcm = self._fallback_tts_pcm(
                    text=text,
                    voice_name=voice_name,
                    character_name=character_name,
                    style=style,
                    pre_cleaned=pre_cleaned,
                    log=log,
                )
                if pcm:
                    self.last_delivery_mode = "fallback"
            if not pcm:
                self.last_error = "No audio data received from Gemini TTS."
                return False
            chunk_size = 4096
            for idx in range(0, len(pcm), chunk_size):
                if should_cancel and should_cancel():
                    break
                on_chunk(pcm[idx:idx + chunk_size])
            return True
        except Exception as exc:
            self.last_error = _friendly_error(exc)
            print(f"[GEMINI TTS] stream_tts failed: {self.last_error}")
            return False

    def _clean_for_tts(self, text: str) -> str:
        """Cleanup disabled — Gemini native audio handles raw text well,
        and prepare_text already converts LaTeX/markdown when used."""
        return text

    def _fallback_tts_pcm(
        self,
        *,
        text: str,
        voice_name: Optional[str],
        character_name: Optional[str],
        style: Optional[str],
        pre_cleaned: bool = False,
        log: Optional[Callable[[str], None]] = None,
    ) -> Optional[bytes]:
        """Fallback path using non-live GenerateContent AUDIO."""
        _log = log or print
        env_models = os.environ.get("GEMINI_TTS_FALLBACK_MODELS", "").strip()
        if env_models:
            models = [m.strip() for m in env_models.split(",") if m.strip()]
        else:
            models = list(DEFAULT_FALLBACK_TTS_MODELS)
        max_attempts = int(os.environ.get("GEMINI_TTS_FALLBACK_RETRIES", "3"))

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            resolved_voice = self._resolve_voice(voice_name, character_name)
            for model in models:
                config = types.GenerateContentConfig(response_modalities=["AUDIO"])
                config.max_output_tokens = 32768
                config.http_options = types.HttpOptions(timeout=30_000)  # 30s
                try:
                    config.speech_config = types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=resolved_voice
                            )
                        )
                    )
                except Exception:
                    pass
                clean_text = text if pre_cleaned else self._clean_for_tts(text)
                payload = (
                    f"Character guidance: {self._resolve_character(character_name)}. "
                    + (f"Additional style guidance: {style}. " if style else "")
                    + self._build_reading_prompt(clean_text)
                )
                for attempt in range(1, max_attempts + 1):
                    try:
                        response = client.models.generate_content(
                            model=model,
                            contents=payload,
                            config=config,
                        )
                        candidates = getattr(response, "candidates", None) or []
                        for candidate in candidates:
                            content = getattr(candidate, "content", None)
                            if not content:
                                continue
                            for part in (getattr(content, "parts", None) or []):
                                inline = getattr(part, "inline_data", None)
                                if inline and getattr(inline, "data", None):
                                    mime_type = getattr(inline, "mime_type", "") or ""
                                    pcm = self._audio_bytes_to_pcm(inline.data, mime_type)
                                    if not pcm:
                                        _log(f"fallback {model} unsupported mime={mime_type!r}")
                                        continue
                                    return pcm
                        _log(f"fallback {model} attempt {attempt}: no audio")
                    except Exception as model_exc:
                        _log(f"fallback {model} attempt {attempt}: {_friendly_error(model_exc)}")
                        if attempt < max_attempts:
                            time.sleep(min(0.4 * (2 ** (attempt - 1)), 2.0))
            return None
        except Exception as exc:
            _log(f"fallback failed: {_friendly_error(exc)}")
            return None

    def _audio_bytes_to_pcm(self, data: bytes, mime_type: str) -> Optional[bytes]:
        """Normalize audio payload to raw PCM s16le mono 24kHz."""
        normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()

        # Gemini live stream chunks are already raw PCM.
        if normalized_mime in ("audio/pcm", "audio/l16", "audio/raw"):
            return data

        # Common fallback path returns WAV container bytes.
        if normalized_mime in ("audio/wav", "audio/x-wav", "audio/wave") or data[:4] == b"RIFF":
            try:
                with wave.open(io.BytesIO(data), "rb") as wf:
                    if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                        print(
                            f"[GEMINI LIVE] unsupported WAV format channels={wf.getnchannels()} sampwidth={wf.getsampwidth()}"
                        )
                        return None
                    # We currently assume 24kHz output path for playback.
                    # If sample rate differs, caller should use file output path instead.
                    if wf.getframerate() != DEFAULT_SAMPLE_RATE:
                        print(f"[GEMINI LIVE] unexpected WAV sample_rate={wf.getframerate()}")
                    return wf.readframes(wf.getnframes())
            except Exception as exc:
                print(f"[GEMINI LIVE] failed to parse WAV payload: {exc}")
                return None

        # Unknown encoded format; avoid passing corrupted bytes to PCM player.
        print(f"[GEMINI LIVE] unsupported fallback mime_type={mime_type!r}")
        return None

    def synthesize_pcm(
        self,
        text: str,
        *,
        voice_name: Optional[str] = None,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
        use_live: bool = False,
        log: Optional[Callable[[str], None]] = None,
    ) -> Optional[bytes]:
        """Generate full PCM payload by streaming and collecting chunks."""
        chunks = []
        ok = self.stream_tts(
            text=text,
            on_chunk=lambda pcm: chunks.append(pcm),
            voice_name=voice_name,
            character_name=character_name,
            style=style,
            use_live=use_live,
            log=log,
        )
        if not ok:
            return None
        return b"".join(chunks)

    def synthesize_wav(
        self,
        text: str,
        *,
        voice_name: Optional[str] = None,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
        use_live: bool = False,
        log: Optional[Callable[[str], None]] = None,
    ) -> Optional[bytes]:
        """Generate WAV bytes."""
        pcm = self.synthesize_pcm(
            text=text,
            voice_name=voice_name,
            character_name=character_name,
            style=style,
            use_live=use_live,
            log=log,
        )
        if not pcm:
            return None
        return pcm_to_wav_bytes(pcm, sample_rate=DEFAULT_SAMPLE_RATE)

    def stream_parallel_wav(
        self,
        text: str,
        *,
        parallelism: int = 4,
        min_buffer_seconds: float = 30.0,
        min_sentence_chars: int = 80,
        min_sentence_chars_growth: float = 2.0,
        chunk_timeout: float = 2.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        voice_name: Optional[str] = None,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
        use_live: bool = False,
        stagger_delay: float = 0.5,
        output_path: Optional[Union[str, pathlib.Path]] = None,
    ) -> Iterator[bytes]:
        """Split text into sentences and synthesize in parallel, yielding WAV chunks in order.

        Sentences are submitted to a thread pool and synthesized concurrently up to
        `parallelism` at a time. Ordered chunks are buffered until `min_buffer_seconds`
        of audio is ready (or all chunks are done), then yielded one at a time.
        Failed sentences are silently skipped.

        Args:
            text:               Full text to synthesize.
            parallelism:        Max concurrent synthesis threads.
            min_buffer_seconds: Minimum seconds of audio to buffer before starting playback.
            voice_name:         Gemini voice override.
            character_name:     Character style to apply.
            style:              Additional style guidance.
            output_path:        Optional path. When provided, all chunks are merged into a
                                single WAV file written to this path after the last chunk
                                is yielded.

        Yields:
            WAV bytes for each sentence, in order.
        """
        sentences = _split_sentences(text, min_chars=min_sentence_chars, growth=min_sentence_chars_growth)
        n = len(sentences)
        if n == 0:
            return

        # WAV header is 44 bytes; PCM data follows. 16-bit mono at DEFAULT_SAMPLE_RATE.
        WAV_HEADER_SIZE = 44

        status = ParallelTTSStatus(n)
        status.start(parallelism, sizes=[len(s) for s in sentences], sentences=sentences)

        results: Dict[int, Optional[bytes]] = {}
        results_lock = threading.Lock()
        done_queue: queue.Queue = queue.Queue()
        work_queue: queue.Queue = queue.Queue()
        cancel_event = threading.Event()
        for i in range(n):
            work_queue.put(i)

        def worker() -> None:
            while True:
                if cancel_event.is_set():
                    return
                try:
                    idx = work_queue.get_nowait()
                except queue.Empty:
                    return
                # Stagger initial API calls to avoid bursting the rate limiter.
                if stagger_delay > 0 and idx < parallelism:
                    cancel_event.wait(timeout=idx * stagger_delay)
                wav = None
                try:
                    sentence = sentences[idx]
                    for attempt in range(1, max_retries + 1):
                        if cancel_event.is_set():
                            break
                        try:
                            wav = self.synthesize_wav(
                                sentence,
                                voice_name=voice_name,
                                character_name=character_name,
                                style=style,
                                use_live=use_live,
                                log=status.set_message,
                            )
                            if wav:
                                break
                        except Exception as exc:
                            delay = _error_retry_delay(exc, retry_delay)
                            err_msg = _friendly_error(exc)
                            if delay is None or attempt == max_retries:
                                status.set_message(f"chunk {idx + 1}: {err_msg}")
                                break
                            status.set_message(f"chunk {idx + 1}: {err_msg}. Retrying in {delay:.0f}s")
                            cancel_event.wait(timeout=delay)
                            continue
                        if not wav and attempt < max_retries:
                            status.set_message(f"chunk {idx + 1}: no audio, retrying ({attempt + 1}/{max_retries}) in {retry_delay:.0f}s")
                            cancel_event.wait(timeout=retry_delay)
                    with results_lock:
                        results[idx] = wav
                    status.mark_received(idx, self.last_delivery_mode if wav else None)
                    if not wav:
                        status.set_message(f"chunk {idx + 1} failed after {max_retries} attempts")
                except Exception as exc:
                    status.set_message(f"chunk {idx + 1}: unexpected error: {exc!s:.60}")
                    with results_lock:
                        results[idx] = None
                    status.mark_received(idx, None)
                finally:
                    done_queue.put(idx)

        for _ in range(min(n, parallelism)):
            t = threading.Thread(target=worker, daemon=True)
            t.start()

        next_idx = 0
        play_buffer = []
        play_deadline: Optional[float] = None  # wall-clock deadline for next chunk
        pcm_parts: list = [] if output_path is not None else None  # type: ignore[assignment]

        try:
            while next_idx < n:
                # Compute remaining time before we give up waiting
                if play_deadline is not None:
                    remaining = play_deadline - time.monotonic()
                    if remaining <= 0:
                        status.set_message(f"Playback timed out")
                        break
                    wait = min(remaining, 1.0)
                else:
                    wait = 120

                try:
                    done_queue.get(timeout=wait)
                except queue.Empty:
                    if play_deadline is not None and time.monotonic() >= play_deadline:
                        status.set_message(f"Playback timed out")
                        break
                    if play_deadline is None:
                        status.set_message("timed out waiting for chunk — thread may be hung")
                        break
                    continue  # deadline not reached yet, keep waiting

                with results_lock:
                    while next_idx < n and next_idx in results:
                        chunk = results.pop(next_idx)
                        play_idx = next_idx
                        next_idx += 1
                        if chunk:
                            play_buffer.append((play_idx, chunk))

                while play_buffer:
                    play_idx, chunk = play_buffer.pop(0)
                    play_deadline = None  # reset: we have something to play
                    status.mark_playing(play_idx)
                    if pcm_parts is not None:
                        pcm_parts.append(chunk[WAV_HEADER_SIZE:])
                    yield chunk
                    status.mark_played()
                    # Start the deadline clock after each chunk finishes playing
                    if next_idx < n:
                        play_deadline = time.monotonic() + chunk_timeout
        finally:
            cancel_event.set()
            status.mute()

        status.finish()

        if output_path is not None and pcm_parts:
            merged_wav = pcm_to_wav_bytes(b"".join(pcm_parts), sample_rate=DEFAULT_SAMPLE_RATE)
            pathlib.Path(output_path).write_bytes(merged_wav)

    async def astream_parallel_wav(
        self,
        text: str,
        *,
        parallelism: int = 4,
        min_buffer_seconds: float = 30.0,
        min_sentence_chars: int = 80,
        min_sentence_chars_growth: float = 2.0,
        chunk_timeout: float = 2.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        voice_name: Optional[str] = None,
        character_name: Optional[str] = None,
        style: Optional[str] = None,
        use_live: bool = False,
        stagger_delay: float = 0.5,
        output_path: Optional[Union[str, pathlib.Path]] = None,
    ) -> AsyncIterator[bytes]:
        """Async version of stream_parallel_wav for use with async web frameworks.

        Sentences are synthesized concurrently in a thread pool executor. Chunks
        are buffered and yielded in order without blocking the event loop.

        **Cancellation**: When the client disconnects, FastAPI raises
        ``asyncio.CancelledError`` inside the generator. The ``finally`` block
        then cancels all queued synthesis tasks (those still waiting on the
        semaphore are aborted immediately; any in-flight Gemini HTTP calls
        complete naturally in their threads but their results are never sent).
        No special handling is needed in the endpoint — disconnection is
        automatic.

        Example (FastAPI)::

            from fastapi import FastAPI, Request
            from fastapi.responses import StreamingResponse
            from pydantic import BaseModel

            app = FastAPI()

            class TTSRequest(BaseModel):
                text: str
                character_name: str | None = None
                parallelism: int = 4

            @app.post("/api/tts/stream")
            async def tts_stream(req: TTSRequest, request: Request):
                \"\"\"Stream parallel TTS audio chunks to the client.

                The response is a chunked WAV stream. Each chunk is a complete
                WAV file (header + PCM) for one sentence. If the client closes
                the connection mid-stream, synthesis of remaining sentences is
                cancelled automatically.
                \"\"\"
                async def generate():
                    async for chunk in api.astream_parallel_wav(
                        req.text,
                        parallelism=req.parallelism,
                        character_name=req.character_name,
                    ):
                        # Stop early if client already disconnected.
                        if await request.is_disconnected():
                            break
                        yield chunk

                return StreamingResponse(generate(), media_type="audio/wav")

        Client-side (JavaScript / fetch)::

            const resp = await fetch("/api/tts/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text, character_name }),
                signal: abortController.signal,   // pass to cancel
            });
            const reader = resp.body.getReader();
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                // value is a Uint8Array containing one WAV chunk — play it
                await playWavChunk(value);
            }

            // To cancel (e.g. stop button):
            abortController.abort();   // closes the connection → server cancels
        """
        sentences = _split_sentences(text, min_chars=min_sentence_chars, growth=min_sentence_chars_growth)
        n = len(sentences)
        if n == 0:
            return

        WAV_HEADER_SIZE = 44

        status = ParallelTTSStatus(n)
        status.start(parallelism, sizes=[len(s) for s in sentences], sentences=sentences)

        loop = asyncio.get_event_loop()
        sem = asyncio.Semaphore(parallelism)
        done_queue: asyncio.Queue = asyncio.Queue()
        results: Dict[int, Optional[bytes]] = {}
        cancel_event = threading.Event()

        async def _cancel_aware_sleep(seconds: float) -> None:
            """Sleep for up to `seconds`, waking early if cancel_event is set."""
            await loop.run_in_executor(None, lambda: cancel_event.wait(timeout=seconds))

        async def synthesize_one(idx: int) -> None:
            async with sem:
                # Stagger initial API calls to avoid bursting the rate limiter.
                if stagger_delay > 0 and idx < parallelism:
                    await _cancel_aware_sleep(idx * stagger_delay)
                wav = None
                try:
                    for attempt in range(1, max_retries + 1):
                        if cancel_event.is_set():
                            break
                        try:
                            wav = await loop.run_in_executor(
                                None,
                                lambda: self.synthesize_wav(
                                    sentences[idx],
                                    voice_name=voice_name,
                                    character_name=character_name,
                                    style=style,
                                    use_live=use_live,
                                    log=status.set_message,
                                ),
                            )
                            if wav:
                                break
                        except Exception as exc:
                            delay = _error_retry_delay(exc, retry_delay)
                            err_msg = _friendly_error(exc)
                            if delay is None or attempt == max_retries:
                                status.set_message(f"chunk {idx + 1}: {err_msg}")
                                break
                            status.set_message(f"chunk {idx + 1}: {err_msg}. Retrying in {delay:.0f}s")
                            await _cancel_aware_sleep(delay)
                            continue
                        if not wav and attempt < max_retries:
                            status.set_message(f"chunk {idx + 1}: no audio, retrying ({attempt + 1}/{max_retries}) in {retry_delay:.0f}s")
                            await _cancel_aware_sleep(retry_delay)
                    results[idx] = wav
                    status.mark_received(idx, self.last_delivery_mode if wav else None)
                    if not wav:
                        status.set_message(f"chunk {idx + 1} failed after {max_retries} attempts")
                except Exception as exc:
                    status.set_message(f"chunk {idx + 1}: unexpected error: {exc!s:.60}")
                    results[idx] = None
                    status.mark_received(idx, None)
                finally:
                    await done_queue.put(idx)

        tasks = [asyncio.create_task(synthesize_one(i)) for i in range(n)]

        next_idx = 0
        play_buffer = []
        play_deadline: Optional[float] = None
        pcm_parts: list = [] if output_path is not None else None  # type: ignore[assignment]

        try:
            while next_idx < n:
                if play_deadline is not None:
                    remaining = play_deadline - time.monotonic()
                    if remaining <= 0:
                        status.set_message(f"Playback timed out")
                        break
                    wait = min(remaining, 1.0)
                else:
                    wait = 120

                try:
                    await asyncio.wait_for(done_queue.get(), timeout=wait)
                except asyncio.TimeoutError:
                    if play_deadline is not None and time.monotonic() >= play_deadline:
                        status.set_message(f"Playback timed out")
                        break
                    if play_deadline is None:
                        status.set_message("timed out waiting for chunk — thread may be hung")
                        break
                    continue

                while next_idx < n and next_idx in results:
                    chunk = results.pop(next_idx)
                    play_idx = next_idx
                    next_idx += 1
                    if chunk:
                        play_buffer.append((play_idx, chunk))

                while play_buffer:
                    play_idx, chunk = play_buffer.pop(0)
                    play_deadline = None
                    status.mark_playing(play_idx)
                    if pcm_parts is not None:
                        pcm_parts.append(chunk[WAV_HEADER_SIZE:])
                    yield chunk
                    status.mark_played()
                    if next_idx < n:
                        play_deadline = time.monotonic() + chunk_timeout
        finally:
            cancel_event.set()
            status.mute()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            status.finish()

        if output_path is not None and pcm_parts:
            merged_wav = pcm_to_wav_bytes(b"".join(pcm_parts), sample_rate=DEFAULT_SAMPLE_RATE)
            pathlib.Path(output_path).write_bytes(merged_wav)

