# Ami: QwenEmotion acting-range audition

Seven sides selected from the installed game's real dialogue export. Source IDs,
original text, script paths, line numbers, labels and scenes are preserved in
`project.json` and checked against the export by audition preparation. No dialogue
was invented. The ordinary-angry and burning-rage cases deliberately reuse the
same line for comparison. The suppression-to-scream direction is an audition
interpretation of a real two-sentence line, not a claim about canonical delivery.

| Case | Source | Emotion route |
| --- | --- | --- |
| 01 Default | `game/script.rpy:477`, `start2` | Prepared `neutral` preset |
| 02 Happy | `game/AmiEvents.rpy:231`, `callamiafternoon` | Prepared `happy` preset |
| 03 Angry | `game/AmiEvents.rpy:5682`, `aminew2` | Prepared `angry` preset |
| 04 Sad | `game/AmiEvents.rpy:4381`, `amidate50p2` | Prepared `sad` preset |
| 05 Suppressed to scream | `game/AmiEvents.rpy:8501`, `amispring1` | Two runtime `arbitrary_emotion` spans |
| 06 Burning rage | `game/AmiEvents.rpy:5682`, `aminew2` | Runtime `arbitrary_emotion` |
| 07 Shattered breakdown | `game/AmiEvents.rpy:8608`, `amispring1` | Three runtime `arbitrary_emotion` spans |

The source's Ren'Py display tags, repeated exclamation marks, display capitals and
elongated nonlexical wail are normalized in cleaning. The wail becomes `Ah!`, not
an invented sentence. Polish preserves that cleaned text exactly and adds emotion
markup. Both stages use the real Codex file exchange and validation; no hand-set
emotion vectors or synthetic validation responses are used. The current Codex
agent performed the two annotation passes; no separate model API was called for
annotation. QwenEmotion alone predicts the backend vectors.

The audition-only profile `profiles/a_index_tts_emotion_audition/pipeline.py` uses
Ami's existing default reference, base speed 1.0, emotion alpha 0.65, deterministic
speech generation, and the prepared QwenEmotion cache. It does not change the
character's production profile. No loudness, pitch or filter processing is added
to manufacture apparent emotion. Extreme acting remains an experiment, not a
guaranteed capability of the eight-dimensional emotion controller.

## Reproduce the accepted reading

In the Conda control environment, from the repository root:

```sh
PYTHONPATH=src python -m lessons_in_cast_core.audition render \
  auditions/ami/emotion-range/project.json \
  --cleaning build/auditions/ami-emotion-range-v1-cleaning \
  --profile profiles/a_index_tts_emotion_audition/pipeline.py \
  --candidate qwen-emotion-alpha-065 \
  --run ami-emotion-range-v1
```

Unchanged successful takes are reused. If inputs change, use a new run name.
The source and casting project is reusable; generated artifacts remain local:

- `build/auditions/ami-emotion-range-v1-cleaning/`: raw dialogue, cleaned responses,
  validation, and the independent `polish/` exchange and accepted tagged text.
- `build/auditions/ami-emotion-range-v1/`: listening sheet, input fingerprints,
  manifest, casting notes and final `takes/*.wav` files.
- `takes/*.segments/`: individual emotion spans, their jobs and runtime
  `.emotion.json` prediction traces for arbitrary emotion.

Listen at a comfortable volume, especially when comparing sudden outbursts.
Successful generation does not by itself establish convincing crying or screaming.

## MiniMax reference-clone comparison

`minimax-plan.json` reuses this exact seven-case project and the already accepted
cleaning and polish results. The comparison profile is
`profiles/a_minimax_emotion_audition/pipeline.py`; the production character mapping
is not changed. The original 12.123-second Ami reference is uploaded unchanged
and cloned once, with server-side denoising and volume normalization disabled.
The clone ID is `lic-ami-ref-ebf3a241c482-v1`. No rejected Voice Design candidate
is used. Reference bytes and upload/clone responses are retained under the new
profile's ignored `assets/clone/` directory, never committed.

MiniMax Speech 2.8 HD does not accept free-form acting prompts. The four primitive
labels use the native emotion mapping; the six descriptions in cases 05--07 use
explicit, agent-authored approximation rules in the MiniMax profile's TOML.
This is not automatic QwenEmotion processing. The backend reports these losses
instead of rewriting the shared polish text or speaking the descriptions.

| Case / span | Native emotion | Additional approximation |
| --- | --- | --- |
| 01 Default | calm | None |
| 02 Happy | happy | None |
| 03 Angry | angry | None |
| 04 Sad | sad | None |
| 05 Restrained | calm | Softer energy, slight breathiness, -3 dB intent |
| 05 Outburst | fearful | Shout approximation, stronger energy |
| 06 Burning rage | angry | Shout approximation, stronger energy |
| 07 Broken apology | sad | Slight breathiness, softer energy |
| 07 Panicked plea | fearful | Slight breathiness, stronger energy |
| 07 Final wail | sad | Shout approximation, stronger energy |

No pitch changes, added dialogue, or inserted sound-effect tokens are used.
Base speed is 1.0. There is no MiniMax equivalent to IndexTTS `emotion_alpha`.
Different model controls mean this is a comparison of backend renderings of the
same intent, not a numerically matched emotion-strength experiment.

Run in the Conda control environment, with a working `ffmpeg` on `PATH`:

```sh
PYTHONPATH=src python scripts/run_minimax_reference_audition.py \
  --plan auditions/ami/emotion-range/minimax-plan.json --dry-run

PYTHONPATH=src python scripts/run_minimax_reference_audition.py \
  --plan auditions/ami/emotion-range/minimax-plan.json
```

The profile reads `MINIMAX_API_KEY` for TTS. A Token Plan subscription key
(`sk-cp-`) is supported; the completed comparison used that route with the existing
cloned voice. Use `--prompt-key` for hidden interactive TTS credential entry.
The cached clone needs no PAYG key, upload or clone request. Creating a new clone
requires `--allow-clone` and a separate `MINIMAX_PAYG_API_KEY` (or
`--prompt-clone-key`); only that operation rejects a subscription key. No automatic
fallback to PAYG occurs. Credentials are not cached or stored in the profile.
Uncertain upload/clone POSTs require inspection instead of automatic retry. Voice
availability and bit-identical remote generation are not guaranteed indefinitely.

The normal audition renderer writes the results to
`build/auditions/ami-emotion-range-minimax-token-plan-v1/`, retaining jobs,
adaptation reports, individual spans, checksums and the listening manifest.
Each synthesized span also retains a `.minimax/response.json` (including original
provider audio and request parameters) and `.minimax/source.wav` before local
resampling. A conversion failure can reuse the provider response without another
TTS call; mismatched cached request parameters fail closed.

The earlier failed run, `ami-emotion-range-minimax-v1`, is preserved. It hit a
missing local `ffmpeg` after receiving the first TTS response; that first response
was not retained by the old adapter. After fixing `PATH`, the PAYG retry was
rejected with `status 1008: insufficient balance`. The earlier instruction to
recharge for TTS was incorrect: switching to the subscription key allowed all
seven cases to finish without another clone. The runner now checks `ffmpeg`
before potentially billable calls, and the adapter retains original provider audio.

API references:

- [Voice cloning](https://platform.minimaxi.com/docs/api-reference/voice-cloning-clone)
- [Speech controls](https://platform.minimaxi.com/docs/api-reference/speech-t2a-http)
- [Pricing and first-use activation](https://platform.minimaxi.com/docs/guides/pricing-paygo)
- [Token Plan coverage and exclusions](https://platform.minimaxi.com/docs/guides/pricing-token-plan)
