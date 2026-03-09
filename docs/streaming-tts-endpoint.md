# Streaming TTS Endpoint with Parallel Synthesis

This guide shows how to expose `astream_parallel_wav` as a FastAPI streaming
endpoint and how to consume it from a browser client with cancellation support.

## How it works

`astream_parallel_wav` splits the input text into sentences, synthesizes them
concurrently (up to `parallelism` at a time), and yields each sentence as a
complete WAV chunk in order. The caller receives audio incrementally instead of
waiting for the entire text to be synthesized.

When the client disconnects mid-stream, the generator exits via
`asyncio.CancelledError`. Any synthesis tasks still queued (waiting on the
semaphore) are cancelled immediately. In-flight Gemini HTTP calls run to
completion in their threads, but their results are never sent.

## Server (FastAPI)

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from gemini_live_tools import GeminiLiveAPI

app = FastAPI()
api = GeminiLiveAPI(api_key="...")


class TTSRequest(BaseModel):
    text: str
    character_name: str | None = None
    parallelism: int = 4


@app.post("/api/tts/stream")
async def tts_stream(req: TTSRequest, request: Request):
    """Stream parallel TTS audio chunks to the client.

    Each chunk in the response is a complete WAV file (44-byte header + PCM)
    for one sentence. If the client closes the connection mid-stream,
    synthesis of remaining sentences is cancelled automatically.
    """
    prepared = api.prepare_text(req.text, character_name=req.character_name)

    async def generate():
        async for chunk in api.astream_parallel_wav(
            prepared,
            parallelism=req.parallelism,
            character_name=req.character_name,
        ):
            # Stop early if client already disconnected.
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(generate(), media_type="audio/wav")
```

> **Note**: `prepare_text` is called before streaming begins. It rewrites the
> text for better TTS quality (punctuation, emphasis hints, etc.) and runs once
> for the full text, not per sentence.

## Client (JavaScript / fetch)

```js
let controller = new AbortController();

async function streamTTS(text, characterName) {
    const resp = await fetch("/api/tts/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, character_name: characterName }),
        signal: controller.signal,   // tied to abort controller
    });

    const reader = resp.body.getReader();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // value is a Uint8Array containing one WAV chunk
        await playWavChunk(value);
    }
}

// Call this from a "Stop" button or when navigating away:
function cancelSpeech() {
    controller.abort();           // closes the connection
    controller = new AbortController();  // reset for next request
}
```

### Playing WAV chunks

Each chunk is a self-contained WAV file. A simple way to play them sequentially:

```js
async function playWavChunk(uint8Array) {
    const audioCtx = new AudioContext();
    const arrayBuffer = uint8Array.buffer;
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioCtx.destination);
    return new Promise(resolve => {
        source.onended = resolve;
        source.start();
    });
}
```

## Cancellation flow

```
Stop button clicked
       │
       ▼
controller.abort()
       │  closes HTTP connection
       ▼
FastAPI raises CancelledError into the generator
       │
       ▼
finally block in astream_parallel_wav:
  - cancels queued asyncio tasks (not yet started)
  - awaits gather(..., return_exceptions=True)
  - in-flight Gemini calls finish in threads but results discarded
```

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `parallelism` | `4` | Max concurrent Gemini TTS calls |
| `min_buffer_seconds` | `30.0` | Seconds of audio to buffer before first yield |
| `min_sentence_chars` | `80` | Merge short sentences until this length |
| `max_retries` | `3` | Retry attempts per sentence on failure |
| `retry_delay` | `1.0` | Seconds between retries |
| `voice_name` | `None` | Gemini voice override |
| `character_name` | `None` | Character style preset |
| `style` | `None` | Additional style guidance |
