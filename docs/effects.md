# Core audio effects

Implementation for [issue #1](https://github.com/5o1/Lessons-in-Cast/issues/1).
Effects operate on synthesized PCM after inline speech segments and ensemble
voices have been assembled, before delivery encoding. They do not change
character identity, profile selection, cleaned words, emotion labels, or a TTS
backend. This first version selects effects per dialogue/render task, not through
new inline speech tags.

## Contract and configuration

`lessons_in_cast_core.effects` exports `EffectSpec`, `EffectLibrary`,
`load_effect_library`, and `CoreEffectProcessor`. The processor implements the
existing backend-neutral `AudioEffectProcessor.process(source, destination,
effects)` contract; `source=None` means an effect-only render. Unknown effects,
unsupported audio, invalid parameters, and unavailable filters raise errors;
there is no silent dry-audio fallback.

`configs/pipeline.toml` selects `effects.config_path = "configs/effects.toml"`.
An explicitly configured missing file is an error. Without a config path, core
defaults are available. Six defaults are supplied in core:

| Preset | Behavior | Main parameters and defaults |
| --- | --- | --- |
| `fade_in` | Linear fade from silence; no trimming | `duration_seconds = 0.15` |
| `fade_out` | Linear fade to silence; no trimming | `duration_seconds = 0.25` |
| `telephone` | Mono, restricted bandwidth, 8 kHz resampling and amplitude quantization | `low_hz = 300`, `high_hz = 3400`, `bits = 8` |
| `monster` | Lower pitch/formants, boost bass, compensate tempo, limit peaks | `semitones = -6`, `bass_db = 6`, `gain_db = -6` |
| `censor_beep` | Replace the interval completely with a sine beep, never mix the original speech into it | `start_seconds = 0`, `end_seconds = -1` (end of clip), `frequency_hz = 1000`, `level_db = -18`, `duration_seconds = 1` (effect-only), `edge_seconds = 0.005` |
| `glitch` | Original fragment → extra repetitions → granular held sound → intermittent dropouts → original normal tail | `position = 0.35`, `chunk_seconds = 0.16`, `repeats = 4`, `gap_seconds = 0.045`, `hold_seconds = 0.8`, `grain_seconds = 0.04`, `dropout_seconds = 0.55`, `gate_on_seconds = 0.065`, `gate_off_seconds = 0.055`, `edge_seconds = 0.004` |

Telephone and monster use FFmpeg, configured through `audio.ffmpeg_executable`.
Other effects use the standard library. The monster implementation uses
[FFmpeg's asetrate and atempo filters](https://ffmpeg.org/ffmpeg-filters.html#asetrate)
for lowered pitch and approximate tempo compensation. It is not formant-preserving
voice design. Telephone is stylized degradation, not an exact telecom codec.
The `.effects.json` audit includes implementation and quality limitations.

All stages accept uncompressed 16-bit PCM WAV, mono/stereo, at least 8 kHz, with
nonempty input and output no longer than 120 seconds. Telephone intentionally
collapses stereo to dual mono. Fades preserve frame count and clamp to the clip
length. All times refer to the audio entering that particular stage; changing
chain order can therefore change both sound and the affected interval.

Custom names refer to core types; chains expand in deterministic left-to-right
order and may contain other chains. Repetition within a chain is allowed. Cycles
and unknown members are rejected. A preset and a chain cannot share a name.

```toml
[presets.deep_entity]
type = "monster"
semitones = -9.0
bass_db = 8.0
gain_db = -8.0

[presets.censor_word]
type = "censor_beep"
start_seconds = 0.6
end_seconds = 1.0

[chains]
fractured_entity = ["deep_entity", "glitch", "fade_out"]
```

To let cleaning choose a custom name, also add it to
`annotation.allowed_effects`. The workspace allowlist now lists implemented
presets and `fractured_entity`, replacing earlier unimplemented placeholders
(`chorus`, `distortion`, `echo`, `reverb`). Old annotations using those names need
an explicit supported treatment; they are not silently reinterpreted.

The existing intermediate JSON remains backend-neutral:

```json
{"action": "speak_with_effect", "spoken_text": "I am still here.", "effects": ["monster", "glitch", "fade_out"]}
```

This is an excerpt, not a complete annotation document. For an effect-only line,
use `action = "sfx_only"`, empty spoken text and an effect chain starting with
`censor_beep`; no TTS job is needed. Fades or pitch processing alone cannot create
audio without a source. Existing annotation review requirements still apply.

## Glitch and censor boundaries

`glitch.position` is a fraction of the current input duration. The fragment is
played once in context, then repeated `repeats` additional times. The last
`grain_seconds` of that fragment is looped for the held and dropout phases.
The untouched continuation resumes after the fragment, with a short anti-click
ramp. No original words are intentionally removed, but output duration increases.
The audit records selected source times, inserted duration and output recovery
time. A clip too short for the requested fragment plus recovery raises an error.

This is granular sound design, not phoneme alignment or semantic vowel stretching.
For the impression of a stuck long vowel, choose a fragment ending in a voiced
sound. A fragment ending in silence or a consonant will produce a different result.

Censor boundaries are explicit times, not word names. The default replaces the
whole line. To censor only a word, configure a named interval after inspecting the
dry take; include a margin around the word, especially before lossy encoding.
The effect is an artistic tool, not a guarantee of irreversible redaction: the
raw synthesis and other build artifacts still contain the original speech.

## CLI and auditions

Activate the project's Conda environment first and make FFmpeg available in PATH.
The installed entry point is `lessons-in-cast-effects`; source-tree usage:

```bash
PYTHONPATH=src python -m lessons_in_cast_core.effects --config configs/effects.toml list
PYTHONPATH=src python -m lessons_in_cast_core.effects --config configs/effects.toml render \
  --input build/path/to/dry.wav --output build/path/to/monster.wav --effects monster fade_out
PYTHONPATH=src python -m lessons_in_cast_core.effects render \
  --output build/path/to/beep.wav --effects censor_beep
PYTHONPATH=src python -m lessons_in_cast_core.effects --config configs/effects.toml audition \
  --input build/path/to/dry.wav --run core-effects-comparison
```

CLI outputs must be new paths/run names. Use `--ffmpeg /path/to/ffmpeg` before the
subcommand if needed. The reusable fixture is `auditions/effects/project.toml`;
all generated audio, copied dry input, listening sheet, manifests and parameter
logs live in `build/auditions/RUN/`. No model or API inference is used by this
comparison command. Regular character auditions also apply effects selected by
validated cleaning, preserving the raw take separately. Their cache fingerprint
includes the effect library, so changed parameters require a new run name.

The initial local comparison is `build/auditions/core-effects-v1/`, using the
previously selected demo1 Ami take as dry input. Automated completion does not
imply listening acceptance. Start at low playback volume, especially for beeps
and intentionally broken speech.

## Artifacts and delivery

Each effected output has a `.effects.json` sibling: resolved ordered steps,
parameters, processor/configuration identity, source/output hashes, duration
changes, FFmpeg version where applicable, and limitations. The main pipeline
retains a consolidated `audio_effects.jsonl` even when intermediate audio is
discarded. No log is created for a run without effects. TTS cache entries remain
dry; the main render stage reapplies current effects on each synthesis run.

The renderer still encodes configured Opus delivery after effects. Ren'Py's RPA
contains only manifest-selected delivery audio at its existing virtual paths,
not these audit logs, reference WAVs or dry intermediates. Effects add no Ren'Py
plugin requirement. Automated tests cover the monster/glitch/fade chain through
PCM, Opus encoding and RPA packing.
