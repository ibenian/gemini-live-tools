# Contributing to gemini-live-tools

## Adding a Voice Character

**Two things to add in `python/gemini_live_tools/gemini_live_api.py`:**

**1. The character description** in the `CHARACTERS` dict:

```python
CHARACTERS: Dict[str, str] = {
    # ... existing characters ...
    "my_character": "My character: brief style description for Gemini to follow.",
}
```

Keep it one sentence. Be specific about cadence, tone, and any accent. Examples from existing characters:
- `"particle_poet"`: *"Particle poet: warm East Coast American accent, slightly informal. Explains the complex with stunning simplicity — finds the perfect everyday analogy every single time. Builds from zero and earns every abstraction. Clear, curious, brilliant."*
- `"rubber_duck"`: *"Rubber duck debugger: talks through the problem slowly out loud, restates assumptions, catches obvious mistakes."*
- `"ivory_tower"`: *"Ivory tower: crisp RP accent — clipped vowels, precise consonants, even syllable stress. Measured cadence, composed delivery. Scholarly authority without pomposity. Clean, formal diction throughout."*

**2. The default voice** in the `CHARACTER_DEFAULT_VOICES` dict:

```python
CHARACTER_DEFAULT_VOICES: Dict[str, str] = {
    # ... existing entries ...
    "my_character": "Kore",   # pick a Gemini voice that fits
}
```

Available Gemini voices: `Kore`, `Charon`, `Fenrir`, `Aoede`, `Puck`, `Leda`, `Orus`, `Zephyr`,
`Iapetus`, `Gacrux`, `Rasalgethi`, `Achird`, `Alnilam`, `Algenib`, `Erinome`, `Achernar`,
`Sadaltager`, `Autonoe`, `Callirrhoe`, `Laomedeia`, `Sadachbia`, `Sulafat`, `Schedar`,
`Despina`, `Umbriel`, `Pulcherrima`.

**3. The UI group** in `js/voice-character-selector.js`:

```js
const CHARACTER_GROUPS = {
    // ...
    my_character: 'Core',  // groups: Core, Academic, Accents, Character, Dramatic, Musical, Fiction
};
```

That's it — open a PR and the character will appear in the voice picker immediately.

---

## License

By submitting a contribution (including pull requests), you agree that your contribution will be licensed under the same MIT License that covers this project.
