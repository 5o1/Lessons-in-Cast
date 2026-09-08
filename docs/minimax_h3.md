# Local MiniMax H3 audio backend

This experimental backend reproduces the **32 × 32 video latent + audio-only decode** approach using native ComfyUI nodes. It runs H3 Ref2VA locally with reference audio. It does not call MiniMax Speech, upload a voice to MiniMax, require an API key, or require a hosted `voice_id`. It still runs the joint audio/video diffusion model; skipping video decoding does not turn it into a small TTS model.

Implementation: `src/lessons_in_cast_core/synthesis/backends/minimax_h3/`.
Example character bundle: `profiles/a_minimax_h3/`. The production character defaults remain unchanged.

## Installation

Use a Conda Python for the project commands. Keep the GPU dependencies in the isolated ComfyUI environment; they are not core dependencies.

```bash
git submodule update --init external/ComfyUI
uv venv --python /path/to/conda/env/bin/python external/ComfyUI/.venv
uv pip install --python external/ComfyUI/.venv/bin/python -r external/ComfyUI/requirements.txt
python scripts/download_minimax_h3.py --proxy http://127.0.0.1:11081 --disable-xet
```

`--disable-xet` uses ordinary resumable HTTP when a proxy fails on Xet chunks. It does not change the proxy node. The downloader retrieves only four components (~42.5 GB), checks their published SHA-256 digests, and writes an ignored `models/Comfy-Org/MiniMax-H3/verified.json`. Startup rejects changed files or a different revision. Source revision is pinned by the Git submodule and checked by the adapter. The worker records installed Python package versions in its build directory. CUDA dependencies add substantial disk usage.

If the proxy also drops long HTTP responses, use `--range-workers 8` instead of `--disable-xet`. This downloads bounded 16 MiB ranges, validates each response's exact byte range, resumes completed pieces after interruption, and checks the final file hash before installing it. Temporary pieces are removed only after successful assembly and verification.

Add this to the **local, ignored** `configs/model_sources.toml`:

```toml
[models.minimax_h3_ref2va_fp8]
path = "models/Comfy-Org/MiniMax-H3"
provider = "huggingface"
repository = "Comfy-Org/MiniMax-H3"
revision = "a98869194787969724c7425d95d0ed73ce9202af"
license = "minimax-h3-community-license-agreement"
```

Supply a reference at `profiles/a_minimax_h3/assets/references/default.wav`. Keep the original source clips in that bundle's `assets/reference_sources/`. All profile assets are ignored by Git. The current local Ami bundle copies the existing Ami reference and its original clips, not a newly synthesized or altered voice.

## Start and render

Start the worker in a separate terminal/process. It listens only on loopback; custom and cloud API nodes are disabled. Model loading is offline after installation. Worker inputs, native outputs, temporary files, package inventory and model provenance are under `build/backends/minimax-h3/8196/`. Stop this dedicated worker with Ctrl-C when finished; profiles do not stop other queued jobs or servers.

```bash
PYTHONPATH=src python -m lessons_in_cast_core.synthesis.backends.minimax_h3 serve \
  --profile-config profiles/a_minimax_h3/config.toml
```

Use the normal audition command, reusing validated cleaning and polish. Ensure `ffmpeg` and `ffprobe` are on PATH (or configured in `configs/pipeline.toml`).

```bash
PYTHONPATH=src python -m lessons_in_cast_core.audition render \
  auditions/ami/emotion-range/project.json \
  --cleaning build/auditions/ami-emotion-range-v1-cleaning \
  --profile profiles/a_minimax_h3/pipeline.py \
  --candidate minimax-h3-ref2va-fp8 \
  --run ami-emotion-range-minimax-h3-v1
```

Use `--case 01-default` for a smoke test, with a different run name. `--reference-audio PATH` temporarily overrides the reference without modifying the bundle. `voice-tags --character a --profile profiles/a_minimax_h3/pipeline.py` on the main CLI lists dynamic voice tags without loading H3.

For a non-blocking first installation, start the documented downloads and environment installation, then run:

```bash
PYTHONPATH=src python scripts/run_minimax_h3_audition.py --wait-for-setup --detach
```

This coordinator waits for verified weights and installed dependencies, starts its own loopback worker, runs the same seven validated Ami cases through the audition CLI, and stops its worker after success. Its state and logs are in `build/backends/minimax-h3/runs/ami-emotion-range-minimax-h3-v1/`. It does not download/install anything itself. A failure leaves any still-running worker intact so a timed-out generation is not destroyed. If a worker already owns the endpoint, use the normal audition CLI instead. Setup waiting has a 12-hour deadline, configurable with `--setup-timeout`.

The adapter saves:

- Standard audition `*.job.json` and `*.adaptation.json`, including the actual prompt, reference paths and feature-approximation report.
- `takes/CASE.minimax-h3/request.json`, `submission.json`, and `history.json`: native node graph, stable queue ID, cache identity and execution outcome.
- `takes/CASE.minimax-h3/native.flac`: untouched native audio, with a SHA-256 receipt. No video is decoded or saved.
- `takes/CASE.wav`: project-format PCM working audio for the existing render/package pipeline. Distribution remains the project's compressed audio format, not WAV.

Queue IDs are persisted **before** submitting. A lost response or polling timeout never silently resubmits a costly GPU job. Rerunning unchanged inputs resumes polling or reuses verified native audio. If the worker was restarted and lost that queue/history, inspect the preserved request and use a new run explicitly. Final normalization can be retried from cached FLAC. No automatic lead-in cropping or removal of generated extra words is performed.

## Controls and compatibility

| Core intent / profile setting | H3 lowering |
| --- | --- |
| Preset emotion | Catalog description, not an IndexTTS vector or H3-specific preset table |
| Arbitrary emotion | The polished natural-language description, passed directly |
| Multiple inline emotions | Ordered dialogue spans inside one joint generation |
| Voice tags | Same-directory audio basenames; reference assets linked to each span |
| Direction, whisper/shout, speed, pitch, qualities, cues | Prompt instructions, explicitly marked approximate |
| Pronunciation dictionary | Phonetic spelling and lexical prosody instructions outside spoken text; approximate |
| `steps`, `seed` | Native sampler settings; default 20 steps, fixed seed |
| `duration_seconds` | Native frame window, rounded to `17*k+5` frames at 24 fps (capped at 345 frames) |

The video canvas is fixed at 32 × 32. The sampler is `res_multistep`, scheduler `simple`, with the pinned FP8 Ref2VA model and NVFP4 text encoder. No Turbo weights are used in this baseline. Changing settings requires a new audition run name.

H3 reference inputs must each be 2–15 seconds, at most three files, **total at most 15 seconds**. This is not IndexTTS's reference-window behavior. The adapter rejects unsupported combinations rather than silently dropping or truncating a voice reference. Output duration is a window, not a speech-length prediction; long dialogue needs upstream segmentation or another backend. Overlong speech can be truncated by the model.

## Experimental limitations and sources

Prompted silence, exact dialogue, voice similarity, timing and acting are not guaranteed. Listen for unrelated lead-in speech, background sound, missing/repeated words, unnatural identity changes and trailing silence. Passing file-format checks is not linguistic or casting acceptance. Physical controls such as pitch and rate are prompt intent, **not calibrated DSP controls**. Preserve and compare the native audio before deciding whether silence trimming is appropriate.

- [Official H3 model card](https://huggingface.co/MiniMaxAI/MiniMax-H3): reference limits and model capabilities.
- [Official reference prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md): six-section conditioning format and voice-reference semantics.
- [Native ComfyUI H3 implementation](https://github.com/Comfy-Org/ComfyUI/blob/efa6c8f804bff78b46a0fd458ebd2e47bba07a30/comfy_extras/nodes_minimax_h3.py): 32-pixel canvas minimum, frame alignment and joint latents.
- [Community native-node audio workflow](https://github.com/SekiyoKana/minimax-studio-webui/blob/main/workflows/minimax_h3_ref2va_fp8_tts_api.json): the minimal-canvas, audio-only decoding approach reproduced here.
- [Independent speech validation notes](https://github.com/T8mars/comfyui-minimax-h3-audio-T8/blob/main/docs/SPEECH_VALIDATION_REPORT.md): exploratory results and reported failure modes, not guarantees for this implementation.

The model uses a [custom H3 community license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE), **not** an unrestricted MIT/Apache model license. Review its territory, commercial and attribution conditions before deployment. Local execution eliminates per-request API charges, not hardware costs, license obligations or rights in reference recordings.
