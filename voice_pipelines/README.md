# Voice pipelines

This directory contains character-specific voice rendering pipelines.

The inheritance structure is intentionally explicit:

```text
VoicePipeline
└── IndexTtsPipeline
    └── ChinamiIndexTtsPipeline
```

The backend-neutral `VoicePipeline` interface lives in
`src/lessons_in_cast/synthesis/voice_pipeline.py`. Reusable backend-family
bases, such as `IndexTtsPipeline`, also live under `src/lessons_in_cast/synthesis`.
This directory contains only game-specific character and strategy modules, such
as `ch_index_tts.py`.

If one character has multiple backends, or multiple rendering strategies for
one backend, create one module per strategy. The active module is selected by
that character's `generation_script_path` in `configs/characters.toml`.

Every module selected by character configuration must export
`create_pipeline(context)`. The loader rejects factories that do not return a
`VoicePipeline`.

Each character pipeline owns a backend-specific TOML below
`configs/voice_pipelines/`. The main `pipeline.toml` remains backend-neutral.

Prepare every configured reference automatically with:

```bash
lessons-in-cast prepare-voices
```

Synthesis calls the same preparation step lazily. Source hashes, processing
settings, and the pipeline ID are stored beside the generated reference so
unchanged references are reused. To override the configured sample directory
for one explicit build, use:

```bash
lessons-in-cast build-reference \
  --character ch \
  --input-dir models/Kakao111/KleeJPGPTSoVits/KleeSamples
```

Without `--output`, the destination declared by that character pipeline is used.
