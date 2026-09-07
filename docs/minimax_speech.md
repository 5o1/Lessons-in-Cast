# MiniMax Speech backend

The reusable MiniMax implementation lives under
`src/lessons_in_cast_core/synthesis/backends/minimax/`. A project profile can
inherit `MiniMaxSpeechPipeline` and provide only its character ID, pipeline ID,
and bundle-local `config.toml`.

The adapter uses MiniMax's synchronous T2A HTTP endpoint and requests a WAV
intermediate. The normal project renderer remains responsible for delivery
encoding and Ren'Py packaging. API credentials are read at runtime from
`MINIMAX_API_KEY` (or the profile's configured environment-variable name) and
are never stored in effective configuration or build provenance.

MiniMax T2A does not expose a free-form, per-utterance acting-prompt field.
Speech 2.8 performance is controlled through its emotion enumeration, voice
settings and modifiers, text sound tags, explicit pause markers, and
pronunciation dictionary. Voice Design prompts create reusable voices and are
not dialogue-direction prompts. The core therefore preserves free-form acting
direction for other backends while the MiniMax adapter reports it as dropped.

## Core feature lowering

| Core intent | MiniMax Speech lowering |
| --- | --- |
| emotion | Native emotion when available; composite labels map to the nearest native emotion |
| exact pause | `<#x#>` when valid; punctuation at text boundaries or for consecutive pauses |
| breath, sigh, laugh, and related events | Speech 2.8 sound tags |
| unsupported event | Comma, ellipsis, or period chosen by event and requested duration |
| speed, volume, global pitch | Native voice settings, clamped to API ranges |
| energy, brightness, clarity | Native voice-modification axes |
| breathiness | Softer energy and volume approximation |
| whisper | Native Speech 2.6 whisper emotion; softer approximation on Speech 2.8 |
| lexical phonemes | `pronunciation_dict` using the best available IPA/kana/romaji form |
| aligned lexical F0 | Per-unit IPA tone-letter approximation; exact core targets remain in provenance |
| per-unit duration | IPA length-mark approximation |

Every conversion decision is emitted to
`build/.../synthesis_adaptations.jsonl` with `exact`, `approximated`, or
`dropped` fidelity. That file makes backend changes reviewable and prevents a
backend's limited controls from silently narrowing the common JSON model.

## Profile example

```python
from lessons_in_cast_core.synthesis.backends.minimax import MiniMaxSpeechPipeline


class CharacterMiniMaxPipeline(MiniMaxSpeechPipeline):
    pipeline_id = "character-minimax-speech-2.8-hd-v1"
    character_id = "character"


def create_pipeline(context):
    return CharacterMiniMaxPipeline(context)
```

The adjacent bundle configuration can contain:

```toml
[backend]
model = "minimax_speech_2_8_hd"
voice_id = "your-cloned-or-system-voice-id"
api_key_environment = "MINIMAX_API_KEY"
language_boost = "English"

[render]
base_speed = 1.0
base_volume = 1.0
base_pitch_semitones = 0
voice_brightness = 0.0
voice_energy = 0.0
voice_clarity = 0.0
```

The hosted model registry entry deliberately omits a local path:

```toml
[models.minimax_speech_2_8_hd]
provider = "minimax-api"
repository = "MiniMax/Speech"
revision = "speech-2.8-hd"
license = "commercial-api-service"
```

References:

- [MiniMax Text-to-Audio HTTP API](https://platform.minimax.io/docs/api-reference/speech-t2a-http)
- [MiniMax model overview](https://platform.minimax.io/docs/guides/models-intro)
