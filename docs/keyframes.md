# Polish keyframe placeholders

Polish may add `keyframe_effects` and local numeric placeholders inside emotion
text. Cleaning must not add them. No preallocated anchor list is needed.

```json
{
  "spoken_text": "<emotion name=\"calm\">{1}Sen{2}sei?{3}</emotion>",
  "keyframe_effects": [{
    "type": "gain_envelope",
    "interpolation": "smooth",
    "keyframes": [
      {"anchor": "1", "gain": 0},
      {"anchor": "2", "gain": 0},
      {"anchor": "3", "gain": 1}
    ]
  }]
}
```

Keep the cleaning action and legacy `effects` unchanged. With this optional field
present, double literal braces (`{{1}}` means literal `{1}`). All declared IDs
must be unique and used; curve points must follow increasing text positions.
Gains are linear amplitudes in [0, 1], not emotion weights. Linear and smoothstep
interpolation are supported; endpoint gains are held outside the curve range.
Multiple gain curves multiply. Plain speech and existing pause offsets stay intact.

The planner removes placeholders before TTS and stores a separate
`RenderTask.keyframe_program`. Changing curves reuses the same dry speech cache.
The renderer aligns the final dry WAV **after** backend splitting, concatenation,
trimming and speed changes, applies envelopes, then legacy effects and encoding.
Chorus/multiple-component keyframe alignment is explicitly unsupported, not guessed.

## Alignment

Whole-audio start/end anchors work without an alignment model. Interior anchors
require `configs/keyframes.toml`. The command receives a JSON request on stdin:
`version`, `audio_path`, `audio_sha256`, `text`, `offsets`, `pronunciations_path`.
It returns `version: 1`, the same `text` and `audio_sha256`, and `boundaries`, each
with `offset`, `time` (seconds), `confidence` and `source`. Offsets count decoded
Unicode characters. Sources are `phone_alignment`, `word_alignment`,
`backend_alignment` or `human_alignment`. Do not interpolate letters into time.

The optional `python -m lessons_in_cast_core.keyframes.mfa --mfa /path/to/mfa
--dictionary /path/to/english.dict --acoustic-model /path/to/english.zip` command
wraps [MFA 3.x align_one](https://montreal-forced-aligner.readthedocs.io/en/v3.3.4/user_guide/workflows/alignment.html).
Supply that argv in `alignment.command` and a `revision` identifying the provider,
model and dictionary versions. MFA and compatible ARPABET models must already be
installed; the project does not download them automatically. Use `--keep-stress`
only if the acoustic model expects stress-bearing phones.

MFA TextGrid output has no calibrated confidence scores. Its adapter returns null,
so using it requires explicitly setting `allow_unscored = true`; do not mistake
this opt-in for confidence validation. Text/phone sequence checks still apply.
For interior word anchors, dictionary `prosody.units` labels must concatenate to
the spelling and their ARPABET must match the aligned phones. Sensei includes such
units: `S/e/n/s/ei`. A boundary inside `ei` is rejected, not guessed.

Measurements are cached under `build/<run>/alignment/cache`, bound to audio bytes,
text, requested offsets, pronunciation file and provider revision. Resolved curves
are recorded in `alignment/<dialogue_id>.json`. Invalid/missing/low-confidence
alignment fails the render; no silent fallback is installed. Preserve old build
directories: the updated polish prompt intentionally invalidates older bindings.

Checks: `PYTHONPATH=src python -m unittest tests.test_keyframes tests.test_polish`.
