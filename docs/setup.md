# Workspace setup

Lessons in Cast is a source-workspace application. The installed Python package
contains reusable orchestration code, while game configuration, prompts,
schemas, and character voice pipelines remain project files at the repository
root. Run the CLI from this checkout or one of its descendants.

## Local installation

Use Python 3.11 or newer for the control process:

```bash
python -m pip install -e .
```

The control process uses the standard library. Speech backends run in their own
environments. Third-party repositories are ignored by Git; their URLs, pinned
commits, roles, and setup notes are recorded in
`external/sources.toml`. Local model directories are also ignored, with their
Hugging Face repositories and revisions recorded in
`configs/model_sources.toml`.

The active IndexTTS checkout uses Python 3.11 and its own environment:

```bash
git clone https://github.com/index-tts/index-tts.git external/index-tts
git -C external/index-tts checkout REVISION_FROM_EXTERNAL_SOURCES_TOML
cd external/index-tts
uv sync --all-extras
```

Download model files at the revisions listed in `configs/model_sources.toml`.
Model licenses remain authoritative and must be reviewed before redistribution.

## Generated files

Generated and downloaded data are intentionally kept out of Git:

```text
build/
├── current/       active restartable pipeline run
├── runs/          named historical and production runs
├── auditions/     listening tests
├── references/    generated model-ready reference audio and manifests
└── archive/       legacy local artifacts

external/          pinned third-party source checkouts
models/            local weights and source samples
game_releases/     local Ren'Py releases used for analysis
```

`lessons-in-cast prepare-voices` constructs or reuses every configured generated
voice dependency. Synthesis also prepares the required character pipeline
lazily, so deleting `build/references/` never requires manual reconstruction.

## Verification

```bash
python -m unittest discover -s tests -t . -v
lessons-in-cast check-config
lessons-in-cast prepare-voices
```

See `docs/pipeline.md` for the complete stage contract and Codex annotation
workflow.
