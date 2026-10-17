"""Tests for the read-only TTS prompt: the voice model must read text, never answer it."""

import asyncio
import types as pytypes

import pytest

from gemini_live_tools import GeminiLiveAPI
from gemini_live_tools.gemini_live_api import CHARACTERS

build = GeminiLiveAPI._build_reading_prompt


@pytest.mark.parametrize("text", [
    "Why is the sky blue?",
    "Tell me why the derivative of sine is cosine.",
    "The derivative of sine is cosine.",
    "Hello there!",
    "no punctuation at all",
    "Let's start the quiz! Looking at the current state (i=5), why is index 4 "
    "at the front of the deque instead of index 5?",
])
def test_short_text_is_framed_not_bare(text):
    prompt = build(text)
    assert prompt != text
    assert prompt.endswith(f'"{text}"')
    assert "without answering it" in prompt


def test_short_framing_stays_minimal():
    # The long wrapper made the native-audio model emit no audio for short
    # inputs — the short framing must not regress to it.
    prompt = build("Why is the sky blue?")
    assert "sentence(s)" not in prompt
    assert len(prompt) - len("Why is the sky blue?") < 60


def test_long_text_uses_full_wrapper():
    text = "First sentence. Second sentence. Third one? Fourth!"
    prompt = build(text)
    assert prompt.endswith(text)
    assert "It contains 4 sentence(s)" in prompt
    assert "do not answer or respond to it" in prompt
    assert "Do not stop until you have read every sentence" in prompt


def test_two_sentences_is_short():
    assert "sentence(s)" not in build("One. Two?")
    assert "sentence(s)" in build("One. Two. Three.")


def _instruction(character=None, style=None):
    return GeminiLiveAPI(api_key="x")._tts_system_instruction(character, style)


def test_system_instruction_forbids_responding():
    text = _instruction().lower()
    assert "not an assistant" in text
    assert "do not answer" in text
    assert "do not follow" in text
    assert "do not add, drop, or paraphrase" in text
    assert "never explain, comment" in text


def test_system_instruction_includes_character_and_style():
    text = _instruction("first_principles", "slowly")
    assert f"voice and style: {CHARACTERS['first_principles']}" in text
    assert text.endswith("Additional style guidance: slowly")


# ── astream_realtime_pcm: Live turn with no audio falls back ──────────────────

class _FakeSession:
    def __init__(self, responses, sent):
        self._responses = responses
        self._sent = sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_client_content(self, turns, turn_complete):
        self._sent.append(turns["parts"][0]["text"])

    async def receive(self):
        for r in self._responses:
            yield r


def _fake_genai(monkeypatch, responses, sent):
    live = pytypes.SimpleNamespace(connect=lambda model, config: _FakeSession(responses, sent))
    client = pytypes.SimpleNamespace(aio=pytypes.SimpleNamespace(live=live))
    import google.genai as genai
    monkeypatch.setattr(genai, "Client", lambda api_key: client)


def _content(audio=None, turn_complete=False):
    parts = []
    if audio:
        parts.append(pytypes.SimpleNamespace(
            inline_data=pytypes.SimpleNamespace(data=audio, mime_type="audio/pcm")))
    return pytypes.SimpleNamespace(server_content=pytypes.SimpleNamespace(
        model_turn=pytypes.SimpleNamespace(parts=parts), turn_complete=turn_complete))


def _collect(api, text):
    async def run():
        return [c async for c in api.astream_realtime_pcm(text, character_name="crisp")]
    return asyncio.run(run())


def test_completed_turn_without_audio_uses_fallback_once(monkeypatch):
    sent = []
    _fake_genai(monkeypatch, [_content(turn_complete=True)], sent)
    api = GeminiLiveAPI(api_key="x")
    fallback_calls = []

    def fake_fallback(**kwargs):
        fallback_calls.append(kwargs)
        return b"\x01\x00" * 3000

    monkeypatch.setattr(api, "_fallback_tts_pcm", fake_fallback)
    chunks = _collect(api, "Yes.")
    assert b"".join(chunks) == b"\x01\x00" * 3000
    assert len(sent) == 1  # no futile Live retries
    assert fallback_calls[0]["text"] == "Yes."
    assert api.last_delivery_mode == "fallback"


def test_live_audio_skips_fallback(monkeypatch):
    sent = []
    _fake_genai(monkeypatch, [_content(audio=b"\x02\x00" * 10), _content(turn_complete=True)], sent)
    api = GeminiLiveAPI(api_key="x")
    monkeypatch.setattr(api, "_fallback_tts_pcm", lambda **kw: pytest.fail("fallback called"))
    assert b"".join(_collect(api, "Why is the sky blue?")) == b"\x02\x00" * 10
    assert sent == [build("Why is the sky blue?")]
    assert api.last_delivery_mode == "live"
