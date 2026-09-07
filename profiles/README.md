# Voice profiles

This directory contains project-defined voice profiles. It behaves like a
user-configurable extension layer, not part of the reusable framework under
`src/`.

A profile is an entrypoint that builds a backend-neutral `VoicePipeline`.
Public contracts, loading, and safe path resolution remain under
`src/lessons_in_cast_core/synthesis/profiles/`. Reusable backend-family
implementations live under `src/lessons_in_cast_core/synthesis/backends/`, while
reference-audio construction and caching live under `synthesis/references/`.

Profiles can use either layout:

```text
profiles/
├── simple_profile.py
└── ch_index_tts/
    ├── pipeline.py
    └── config.toml
```

A single-file profile may keep all settings in Python. A bundle profile can own
configuration and other resources beside its entrypoint. The loader supplies a
`VoiceProfileContext`; `context.resolve_resource(...)` resolves bundle-relative
paths and rejects paths that escape the bundle.

Every configured entrypoint must export:

```python
def create_pipeline(context: VoiceProfileContext) -> VoicePipeline:
    ...
```

The active default is selected by `default_voice_profile` in
`configs/characters.toml`. Character configuration contains no model,
reference-audio, speaking-rate, or backend settings. Those belong to the
profile. A character may select contextual defaults through nested tables in
`configs/characters.toml`, ordered as source path, nearest label, and nearest
scene. Per-dialogue profile overrides are intentionally not implemented yet.

The project currently configures one IndexTTS bundle for each of its 33
selected character voices. Every bundle uses this inheritance structure:

```text
VoicePipeline
└── IndexTtsPipeline
    └── Character-specific IndexTtsPipeline
```

Each `config.toml` owns the IndexTTS model ID, `base_speed`, inference
settings, pronunciation rules, reference source, and generated-reference
destination. Values above `1.0` make `base_speed` faster; values below `1.0`
make it slower. The runtime registry in `configs/model_sources.toml` owns each
model's local path, provider, repository, revision, and license. The profile
configuration itself is located relative to `pipeline.py`.
Reference assets set `scope` to `profile` and live below the bundle's
`assets/` directory. That directory is ignored by Git so audio is never pushed
to the remote; tracked configuration records only neutral relative filenames
and their order.

Newly sourced voices begin as initial candidate profiles. Their ignored
`assets/reference_sources/manifest.json` records source URLs and identity
notes locally. Audition and curate those sources before treating a profile as
final; the presence of a bundle means it is routable, not that its casting or
reference mix has passed subjective review.

Hosted backends use the same profile contract. A MiniMax bundle inherits
`MiniMaxSpeechPipeline`, keeps its `voice_id` and rendering defaults in the
bundle-local configuration, and refers to `speech-2.8-hd` by registry model ID.
It does not contain an API secret or local model path. See
`docs/minimax_speech.md` for the configuration and feature-lowering contract.

Prepare every configured reference automatically with:

```bash
lessons-in-cast prepare-voices
```

Synthesis performs the same preparation lazily. A present curated reference
is used byte-for-byte; when it is missing, the ordered local source files are
combined into the configured profile asset.

To build a reference from another sample directory explicitly:

```bash
lessons-in-cast build-reference \
  --character ch \
  --input-dir path/to/samples
```

Without `--output`, the destination declared by the selected profile is used.
