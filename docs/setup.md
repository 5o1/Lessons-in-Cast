# Workspace setup

Lessons in Cast is a source-workspace application. The installed Python package
contains reusable orchestration code, while game configuration, prompts, and
character voice profiles remain project files under `profiles/` at the
repository root. Run the CLI from this checkout or one of its descendants.

## Local installation

Use Python 3.11 or newer for the control process:

```bash
python -m pip install -e .
```

The control process uses the standard library. Speech backends run in their own
environments. Final Opus encoding and validation require `ffmpeg` and `ffprobe`
with libopus support on `PATH`; their commands and speech bitrate are configurable
in `configs/pipeline.toml`. Third-party repositories are tracked as Git submodules: their URLs
are stored in `.gitmodules`, their revisions are pinned by the parent gitlinks,
and project-specific roles and setup notes are recorded in
`external/sources.toml`. Local model directories remain ignored. The runtime
model registry in the ignored local file `configs/model_sources.toml` maps
stable model IDs to local paths and records their providers, repositories,
revisions, and licenses. Voice profiles select models through those IDs. Create
it from the tracked
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
└── auditions/     listening tests

profiles/*/assets/ local reference audio and ordered source clips
external/          third-party submodule worktrees pinned by the parent repo
models/            local weights and source samples
game_releases/     local game releases used for analysis
```

`lessons-in-cast prepare-voices` validates or rebuilds every configured voice
reference. Synthesis does the same lazily. Profile asset directories are ignored
by Git and must be backed up or reconstructed from locally retained sources;
they are never uploaded with the repository.

## Verification

```bash
python -m unittest discover -s tests -t . -v
lessons-in-cast check-config
lessons-in-cast prepare-voices
```

See `docs/pipeline.md` for the complete stage contract and Codex annotation
workflow.

See [voice design](voice-design.md) for the separate VoxCPM2 reference-audition
module, local model setup, and its backend-environment CLI.

## Experimental local H3 backend

See [Local MiniMax H3 audio](minimax_h3.md) for the isolated ComfyUI environment,
pinned reference-conditioned weights, loopback worker and normal audition commands.
