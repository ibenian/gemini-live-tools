# Streaming TTS Endpoint with Parallel Synthesis

This guide shows how to expose `astream_parallel_wav` as a FastAPI streaming
endpoint and how to consume it from a browser client with cancellation support.

## How it works

`astream_parallel_wav` splits the input text into sentences, synthesizes them
concurrently (up to `parallelism` at a time), and yields each sentence as a
complete WAV chunk in order. The caller receives audio incrementally instead of
waiting for the entire text to be synthesized.

### Chunk sizing strategy

Chunks are sized with a growing minimum-character threshold controlled by
`min_sentence_chars` and `min_sentence_chars_growth`:

```
chunk 0 threshold: min_sentence_chars
chunk 1 threshold: min_sentence_chars × growth
chunk 2 threshold: min_sentence_chars × growth²
…
```

With the default `growth=2.0`, each chunk is at least twice as long as the
previous one. This serves two goals:

**Latency**: Chunk N+1 takes longer to synthesize than chunk N, but chunk N's
synthesis finishes before chunk N-1 finishes playing. By the time the listener
hears chunk 0, chunks 1 and 2 are already done — playback is seamless with no
gaps.

**Quota efficiency**: Fewer, larger API calls cover the same total text.
Instead of one call per sentence, you make roughly log₂(total_chars /
min_sentence_chars) calls. This keeps requests-per-minute consumption low,
which matters when synthesizing long texts under quota limits.

The last chunk is merged into the previous one if it is smaller than 50% of it.
This prevents a short straggler from becoming a bottleneck at the end and
ensures chunk sizes grow monotonically.

Example output with `min_sentence_chars=20, growth=2`:
```
[TTS-Parallel] 5 chunks (18, 43, 91, 188, 203), parallelism=4
```

Progress is displayed via `ParallelTTSStatus` — a reusable, thread-safe class
that renders a single updating status line:

```
[TTS-Parallel] Received 4/8 [▶ L   * L] Playing 1/8
```

Icons: `▶` = currently playing, `L` = received via Live API, `*` = received via
generate_content fallback, `!` = failed, ` ` = pending.

Both `stream_parallel_wav` and `astream_parallel_wav` use it internally. You
can also import and use it directly for your own streaming loops:

```python
from gemini_live_tools import ParallelTTSStatus

status = ParallelTTSStatus(n=total_chunks)
status.start(parallelism=4)
status.mark_received(idx, delivery_mode="live")      # L icon
status.mark_received(idx, delivery_mode="fallback")  # * icon
status.mark_received(idx, delivery_mode=None)        # ! icon (failure)
status.mark_playing(idx)
status.mark_played()
status.finish()
```

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
| `min_sentence_chars` | `80` | Minimum characters for the first chunk |
| `min_sentence_chars_growth` | `2.0` | Multiply threshold by this factor each chunk (`1.0` = no growth) |
| `max_retries` | `3` | Retry attempts per sentence on failure |
| `retry_delay` | `1.0` | Seconds between retries |
| `use_live` | `False` | Use Gemini Live API for synthesis; falls back to `generate_content` on failure. Status line shows `L` (live) or `*` (fallback) per chunk. |
| `voice_name` | `None` | Gemini voice override |
| `character_name` | `None` | Character style preset |
| `style` | `None` | Additional style guidance |

---

# Realtime Streaming TTS (Low-Latency)

For the lowest possible time-to-first-audio (~200-500ms), use the realtime
streaming methods. Unlike the parallel pipeline above, these send the entire
text in a **single Live API websocket session** and yield raw PCM chunks as
they arrive — no sentence splitting, no buffering, no multiple API calls.

## How it works

```
Text  ──►  Live API websocket  ──►  PCM chunks yielded as they arrive
                                          │
                              ┌────────────┴────────────┐
                              ▼                         ▼
                    CLI: sounddevice            FastAPI: HTTP stream
                    OutputStream.write()        StreamingResponse
```

1. A single Live API session is opened with character voice + style config
2. The full text is sent as one message
3. As the model generates audio, PCM chunks (s16le mono 24kHz, typically 1-4KB
   each = ~20-80ms of audio) arrive via websocket
4. Each chunk is yielded immediately — no waiting for completion

## API

### Async (for FastAPI / aiohttp)

```python
from gemini_live_tools import GeminiLiveAPI

api = GeminiLiveAPI(api_key="...")

async for pcm_chunk in api.astream_realtime_pcm(
    text,
    character_name="crisp",
    voice_name="Kore",         # optional override
    style="speak slowly",      # optional
    timeout=60.0,              # total session timeout
    log=print,                 # optional debug logging
):
    # pcm_chunk is raw bytes (s16le mono 24kHz)
    yield pcm_chunk
```

### Sync (for CLI / scripts)

```python
for pcm_chunk in api.stream_realtime_pcm(
    text,
    character_name="crisp",
    voice_name="Kore",
    style="speak slowly",
    timeout=60.0,
    log=print,
):
    # feed to sounddevice, write to file, etc.
    stream.write(np.frombuffer(pcm_chunk, dtype=np.int16))
```

The sync variant runs the async generator in a background thread with a queue,
so it works in non-async contexts without blocking the event loop.

## FastAPI endpoint

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from gemini_live_tools import GeminiLiveAPI, pcm_to_wav_bytes

app = FastAPI()
api = GeminiLiveAPI(api_key="...")


class RealtimeTTSRequest(BaseModel):
    text: str
    character_name: str | None = None
    voice_name: str | None = None
    style: str | None = None


@app.post("/api/tts/realtime")
async def tts_realtime(req: RealtimeTTSRequest, request: Request):
    """Stream realtime TTS audio with lowest latency.

    Response is a stream of raw PCM s16le mono 24kHz bytes.
    Client should feed directly to an AudioWorklet or ScriptProcessorNode.
    """
    async def generate():
        async for pcm_chunk in api.astream_realtime_pcm(
            req.text,
            character_name=req.character_name,
            voice_name=req.voice_name,
            style=req.style,
        ):
            if await request.is_disconnected():
                break
            yield pcm_chunk

    return StreamingResponse(
        generate(),
        media_type="audio/pcm",
        headers={
            "X-Audio-Sample-Rate": "24000",
            "X-Audio-Channels": "1",
            "X-Audio-Format": "s16le",
        },
    )
```

## JavaScript client (Web Audio API)

Raw PCM streaming requires an AudioWorklet or ScriptProcessorNode to play
chunks as they arrive:

```js
let controller = new AbortController();

async function streamRealtimeTTS(text, characterName) {
    const audioCtx = new AudioContext({ sampleRate: 24000 });

    // Create a ScriptProcessorNode for buffered playback
    const bufferSize = 4096;
    const processor = audioCtx.createScriptProcessor(bufferSize, 1, 1);
    const pcmQueue = [];
    let queueOffset = 0;

    processor.onaudioprocess = (e) => {
        const output = e.outputBuffer.getChannelData(0);
        for (let i = 0; i < output.length; i++) {
            if (pcmQueue.length > 0) {
                const chunk = pcmQueue[0];
                output[i] = chunk[queueOffset++] / 32768;  // s16le to float
                if (queueOffset >= chunk.length) {
                    pcmQueue.shift();
                    queueOffset = 0;
                }
            } else {
                output[i] = 0;  // silence while waiting
            }
        }
    };
    processor.connect(audioCtx.destination);

    // Fetch and stream PCM
    const resp = await fetch("/api/tts/realtime", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, character_name: characterName }),
        signal: controller.signal,
    });

    const reader = resp.body.getReader();
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Convert Uint8Array (s16le bytes) to Int16Array
        const int16 = new Int16Array(value.buffer, value.byteOffset, value.byteLength / 2);
        pcmQueue.push(int16);
    }

    // Wait for queue to drain, then clean up
    await new Promise(resolve => {
        const check = setInterval(() => {
            if (pcmQueue.length === 0) {
                clearInterval(check);
                processor.disconnect();
                resolve();
            }
        }, 100);
    });
}

function cancelSpeech() {
    controller.abort();
    controller = new AbortController();
}
```

## CLI usage

```bash
gstts -rt "Hello world"                    # realtime with default character
gstts -rt -c narrator "Hello world"        # realtime with specific character
gstts -rt -p "text with markdown"          # prepare first, then realtime
gstts -rt --output out.wav "Hello"         # realtime playback + save to file
```

## Comparison: parallel vs realtime

| | Parallel (`stream_parallel_wav`) | Realtime (`stream_realtime_pcm`) |
|---|---|---|
| **Time-to-first-audio** | 3-10s | ~200-500ms |
| **API calls** | N (one per sentence chunk) | 1 (single session) |
| **Output format** | WAV chunks (with headers) | Raw PCM (s16le 24kHz) |
| **Buffering** | Configurable (`min_buffer_seconds`) | None — plays immediately |
| **Best for** | Long texts, reliable playback | Short-medium text, low latency |
| **Cancellation** | Per-chunk, queued tasks cancelled | Immediate, single session closed |

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `text` | required | Text to synthesize (pre-processed if desired) |
| `voice_name` | `None` | Gemini voice override |
| `character_name` | `None` | Character style preset |
| `style` | `None` | Additional style guidance |
| `timeout` | `60.0` | Total session timeout in seconds |
| `log` | `None` | Callback for debug messages |
