# Emotion presets and arbitrary emotion

Core labels describe acting, not backend axes or numerical strengths. Built-in
definitions live in `src/lessons_in_cast_core/emotions.py`. Workspace additions
and explicit description overrides live in `configs/emotions.toml`. Catalog
loading does not mutate the process-global built-ins.

## Register and prepare a preset

Run commands in the project's Conda control environment, with `PYTHONPATH=src`:

```sh
python -m lessons_in_cast_core emotion-presets list
python -m lessons_in_cast_core emotion-presets add nervous_reassurance \
  --description "Offering reassurance while audible nervousness remains." \
  --example "It will be all right. I promise."
python -m lessons_in_cast_core emotion-presets prepare --backend index-tts
```

Registration requires one unique semantic name, a description and an example.
It does not silently overwrite existing names. Edit the TOML explicitly to revise
a definition. After preparing the required backends, enable the label in
`configs/pipeline.toml` under `annotation.allowed_emotions`. Polish receives the
selected definitions and examples. Other backends must implement their own
mapping before the new label can be rendered there.

The public preparation contract is `EmotionPresetPreprocessor.prepare(catalog,
output, force=False)` in `emotion_presets.py`. IndexTTS implements it in
`synthesis/backends/index_tts/emotion_preparation.py`. Only IndexTTS preparation
is implemented in the CLI currently; this does not claim automatic MiniMax or
GPT-SoVITS mapping support.

## IndexTTS preparation

The default input is each label's description, not its name or example dialogue.
The default backend configuration is `profiles/a_index_tts/config.toml`; override
it with `--profile PATH`. It resolves the model ID through the local model registry
and uses the backend's Python environment. No character reference, speech model,
online service or speech generation is required.

```sh
python -m lessons_in_cast_core emotion-presets prepare --backend index-tts \
  --profile profiles/a_index_tts/config.toml \
  --input-kind description \
  --output build/cache/index-tts/emotion-vectors.json
```

`--input-kind example` and `combined` permit comparisons; use separate output
paths to retain each experiment. `--force` regenerates all predictions. Otherwise
unchanged labels are reused without loading QwenEmotion. Changed inputs/model
fingerprints trigger regeneration. Interrupted runs retain per-label checkpoints
in `.partial`; the final file is atomically published only after all labels pass.
Do not run concurrent writers against the same output path.

Each entry retains its semantic definition, exact input, raw generated text,
parsed eight-axis prediction, normalized vector and provenance key. Metadata binds
the registered model/revision, local model/tokenizer/config hashes, upstream code
and predictor implementation. The vector order is:

`happy, angry, sad, afraid, disgusted, melancholic, surprised, calm`.

The adapter applies the existing IndexTTS bias and total-strength cap once; profile
`emotion_alpha` remains a separate inference control. Vectors are not probabilities.
Malformed/empty, nonnumeric, nonfinite, out-of-range or truncated predictions fail
instead of being silently replaced with a neutral voice. Failure diagnostics are
saved beside the cache. Identical vectors across distinct labels produce warnings;
automatic generation is not listening calibration.

To use a prepared cache, add this to a profile's existing `[backend]` table:

```toml
emotion_vectors_path = "build/cache/index-tts/emotion-vectors.json"
```

This path is repository-relative. Missing, incomplete, stale or corrupt caches
are errors, never silent manual-preset fallbacks. The mapping identity and effective
vectors participate in synthesis cache keys. Omitting the setting retains the
existing manual mapping explicitly; preparation by itself does not edit profiles.
Generated files remain ignored under `build/`.

## Runtime arbitrary emotion

Polish may describe a performance that is not represented by a reusable preset:

```xml
<arbitrary_emotion description="Trying to sound cheerful while holding back tears.">I'm fine.</arbitrary_emotion>
```

The description is portable acting intent. It is not spoken, not a new preset
name, and not written to the preset cache. This is part of the schema-5 polish
contract, not the text-cleaning step.

Every span has exactly one of these forms:

```xml
<emotion name="tearful_resolve">I'll try again.</emotion>
<arbitrary_emotion description="A brittle laugh disguising sudden panic.">Of course.</arbitrary_emotion>
```

They can be adjacent or inside a `<voice name="...">` wrapper. They cannot nest,
overlap, carry each other's attributes, or both control the same speech segment.
Empty descriptions are invalid. Escape XML attribute characters. Both the markup
validator and typed job/segment API enforce exclusivity.

IndexTTS planning retains the description and does not run a model. At synthesis
time, the worker lazily loads QwenEmotion once, resolves each arbitrary description
to a vector using the same strict predictor, then generates that segment. Different
descriptions remain distinct segments; adjacent equal descriptions/voice controls
may merge. The resulting audio is concatenated in order as usual. A `.emotion.json`
sidecar records the runtime prediction for inspection, not reuse as a preset.
Normal synthesized-audio caching still applies and hashes the description.

MiniMax and GPT-SoVITS currently reject arbitrary emotion explicitly; their
backend-specific lowering is future work. This prevents silently losing direction.
