# gemini-live-tools

Python library for Gemini Live TTS with voice characters, and safe math expression evaluation.

## Contents

```
python/                        Python package
  gemini_live_tools/
    gemini_live_api.py         GeminiLiveAPI, character definitions, PCM/WAV helpers
    math_eval.py               Safe AST-based math expression evaluator
  gstts.py                     Gemini Streaming TTS CLI

js/
  voice-character-selector.js  Drop-in voice/character picker UI widget

docs/
  streaming-tts-endpoint.md   FastAPI streaming endpoint guide with cancellation

gstts.sh                       Gemini Streaming TTS CLI
```

## gstts — Gemini Streaming Text-to-Speech CLI

### Quick start

```bash
# First time: set up venv and install the `gstts` command system-wide
./gstts.sh setup

# After setup, use `gstts` from anywhere
gstts "Hello world"                             # read text aloud (uses default character)
gstts                                           # interactive: pick a character, generate & play a greeting
```

The venv is auto-created on first run if you skip setup — but `setup` also installs a
`/usr/local/bin/gstts` symlink so you can call it from any directory.

### Characters and voices

```bash
gstts -lc                                       # list available characters
gstts -lv                                       # list available Gemini voices
gstts "Hello" -c narrator                       # use a specific character
gstts "Hello" -c narrator -v Charon             # character + voice override
gstts "Hello" -s "speak slowly and dramatically"  # add a style instruction
```

In the interactive picker, **Enter** selects a character and proceeds to TTS.
**Space** sets the character as default in `~/gstts_config.json` and exits
(quick-select mode — no audio generated).

### Prepare mode

By default, provided text is read as-is. Use `-p` to rewrite the text into
speech-friendly form via Gemini before synthesis:

```bash
gstts -p "The API returns 200 OK w/ a JSON payload incl. nested arrays"
```

### Options

```bash
gstts "text" --no-live                          # disable Live API (use generate_content)
gstts "text" --parallelism 4                    # parallel TTS (4 concurrent chunks)
gstts "text" --output greeting.wav              # save audio to file
gstts "text" --debug                            # verbose output
gstts --parallelism 4 --min-sentence-chars 60 --min-buffer-seconds 10
```

### Config

Character preference is stored in `~/gstts_config.json`:

```json
{ "character": "crisp" }
```

When text is passed without `--character`, the config character is used automatically.
After picking from the menu, you're prompted to save the selection as the new default.

### Development

```bash
./gstts.sh setup                                # create .venv, install deps, symlink /usr/local/bin/gstts
./gstts.sh shell                                # drop into a shell with the .venv activated
```

## Install (Python)

Always pin to a tagged release — do not reference `main` directly as it may contain unreleased changes.

```bash
# Pin to a specific release tag (recommended)
pip install "gemini-live-tools @ git+https://github.com/ibenian/gemini-live-tools.git@v0.1.6#subdirectory=python"
```

To find the latest tag:

```bash
git ls-remote --tags https://github.com/ibenian/gemini-live-tools.git | grep -v '\^{}' | awk -F/ '{print $3}' | sort -V | tail -1
```

## Usage

```python
from google import genai
from gemini_live_tools import GeminiLiveAPI, ParallelTTSStatus
from gemini_live_tools import safe_eval_math, eval_math_sweep, MATH_NAMES

client = genai.Client(api_key="...")
api = GeminiLiveAPI(api_key="...", client=client)

# Single-shot TTS
prepared = api.prepare_text("Hello world", character_name="crisp")
wav = api.synthesize_wav(prepared, character_name="crisp")

# Single-shot TTS via Live API (falls back to generate_content on failure)
wav = api.synthesize_wav(prepared, character_name="crisp", use_live=True)

# Parallel streaming TTS (sync — yields one WAV chunk per sentence in order)
for chunk in api.stream_parallel_wav(prepared, parallelism=4, character_name="crisp"):
    play(chunk)   # play each sentence as it arrives

# Parallel streaming TTS with Live API
for chunk in api.stream_parallel_wav(prepared, parallelism=4, character_name="crisp", use_live=True):
    play(chunk)

# Parallel streaming TTS (async — for FastAPI / aiohttp)
async for chunk in api.astream_parallel_wav(prepared, parallelism=4, character_name="crisp"):
    yield chunk

# Use ParallelTTSStatus standalone for your own streaming loops
status = ParallelTTSStatus(n=total_chunks)
status.start(parallelism=4)
status.mark_received(idx=0, delivery_mode="live")     # L icon — received via Live API
status.mark_received(idx=1, delivery_mode="fallback") # * icon — received via generate_content
status.mark_playing(idx=0)             # shows ▶ on status line
status.mark_played()
status.finish()                        # prints final Played N/N line

# Math eval
result, err = safe_eval_math("norm([3, 4])")   # → 5.0
result, err = safe_eval_math("sin(pi/2)")       # → 1.0
```

See [docs/streaming-tts-endpoint.md](docs/streaming-tts-endpoint.md) for a full FastAPI streaming endpoint example with client-side cancellation.

## JS Widget

`js/voice-character-selector.js` is a self-contained browser widget that exposes `window.GeminiVoiceCharacterSelector`. It provides two components:

**`CharacterPicker`** — a searchable, grouped character palette (like a command palette). Features:
- Opens via a trigger button or `Cmd+K` / `Ctrl+K`
- Live search across character name, label, and group
- Characters organized into groups: Core, Academic, Accents, Dramatic, Musical, Fiction, etc.
- Tracks recently used characters
- Persists selection to `localStorage`

**`setupVoiceSelect`** — populates a `<select>` element with all available Gemini voices, with optional `localStorage` persistence.

### Setup

Copy the file into your project and include it:

```html
<script src="/static/voice-character-selector.js"></script>
```

### HTML

```html
<button id="characterBtn">Character</button>
<select id="voiceSelect"></select>

<!-- Palette and backdrop should be direct children of body for correct positioning -->
<div id="characterPalette" class="style-palette" hidden>
    <input id="characterSearch" class="style-search" type="text" placeholder="Search characters..." />
    <div id="characterList" class="style-list"></div>
</div>
<div id="characterBackdrop" class="style-backdrop" hidden></div>
```

### JavaScript

```js
const lib = window.GeminiVoiceCharacterSelector;

// Move palette and backdrop to body so they're never clipped by overflow/stacking contexts
document.body.appendChild(document.getElementById('characterPalette'));
document.body.appendChild(document.getElementById('characterBackdrop'));

// Populate voice <select> — returns the currently selected voice
let selectedVoice = lib.setupVoiceSelect(document.getElementById('voiceSelect'), {
    storageKey: 'myAppVoice',
    defaultValue: 'Charon',
});

// Wire up the character picker
let selectedCharacter = 'crisp';
const picker = new lib.CharacterPicker({
    buttonEl:   document.getElementById('characterBtn'),
    paletteEl:  document.getElementById('characterPalette'),
    searchEl:   document.getElementById('characterSearch'),
    listEl:     document.getElementById('characterList'),
    backdropEl: document.getElementById('characterBackdrop'),
    options:    lib.CHARACTER_OPTIONS,
    groupMap:   lib.CHARACTER_GROUPS,
    groupOrder: lib.CHARACTER_GROUP_ORDER,
    storageKey: 'myAppCharacter',
    recentsKey: 'myAppCharacterRecents',
    defaultId:  'crisp',
    hotkey:     'k',  // opens palette on Cmd/Ctrl+K
    onChange: (characterId) => {
        selectedCharacter = characterId;
        // auto-switch voice to the character's recommended default
        const opt = lib.CHARACTER_OPTIONS.find(o => o.id === characterId);
        if (opt?.defaultVoice) {
            document.getElementById('voiceSelect').value = opt.defaultVoice;
            selectedVoice = opt.defaultVoice;
        }
    },
});
selectedCharacter = picker.init();
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add voice characters and more.

---

## Requirements

- Python 3.10+
- `google-genai >= 1.27.0`
- `numpy >= 1.26.0`
- `simple-term-menu >= 1.6.0`
- `GEMINI_API_KEY` environment variable

---

## License

[MIT](LICENSE)

## Disclaimer

This software is provided for educational and informational purposes only. The authors and contributors make no representations or warranties regarding the accuracy, completeness, or suitability of this software for any particular purpose. Use is entirely at your own risk. The authors shall not be held liable for any direct, indirect, incidental, special, or consequential damages arising from the use of or inability to use this software.
