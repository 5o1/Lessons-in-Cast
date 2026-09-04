# Workspace setup

Lessons in Cast is a source-workspace application. The installed Python package
contains reusable orchestration code, while game configuration, prompts, and
character voice pipelines remain project files at the repository root. Run the
CLI from this checkout or one of its descendants.

## Local installation

Use Python 3.11 or newer for the control process:

```bash
python -m pip install -e .
```

The control process uses the standard library. Speech backends run in their own
environments. Third-party repositories are tracked as Git submodules: their URLs
are stored in `.gitmodules`, their revisions are pinned by the parent gitlinks,
and project-specific roles and setup notes are recorded in
`external/sources.toml`. Local model directories remain ignored, with their
Hugging Face repositories and revisions recorded in the ignored local file
`configs/model_sources.toml`. Create it from the tracked
`configs/model_sources.default.toml` template.

Clone the workspace and its external projects together:

```bash
git clone --recurse-submodules <repository-url>
```

For an existing clone, initialize or synchronize them with:

```bash
git submodule update --init --recursive
```

The active IndexTTS checkout uses Python 3.11 and its own environment:

```bash
cd external/index-tts
uv sync --all-extras
```

Download model files at the revisions listed in the local
`configs/model_sources.toml`. Model licenses remain authoritative and must be
reviewed before redistribution.

## Generated files

Generated and downloaded data are intentionally kept out of Git:

```text
build/
├── current/       active restartable pipeline run
├── runs/          named historical and production runs
├── auditions/     listening tests
└── references/    generated model-ready reference audio and manifests

external/          third-party submodule worktrees pinned by the parent repo
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
