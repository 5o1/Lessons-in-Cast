# Voice design

`lessons_in_cast_core.voice_design` creates character-reference auditions,
independently of dialogue extraction, annotation, and production synthesis.
Its public `VoiceDesigner` contract takes a `VoiceDesignRequest` and produces a
`VoiceDesignResult`. Backend-specific controls live in the adapter settings,
not in the spoken script or character configuration.

The first adapter is `VoxCPM2VoiceDesigner`, backed by the official
[OpenBMB/VoxCPM source](https://github.com/OpenBMB/VoxCPM) and
[VoxCPM2 weights](https://huggingface.co/openbmb/VoxCPM2).

## Local setup

Source code is pinned as the `external/VoxCPM` Git submodule. Weights belong in
`models/openbmb/VoxCPM2`, not in the source checkout. Register the downloaded
snapshot in the ignored `configs/model_sources.toml`:

```toml
[models.voxcpm2]
path = "models/openbmb/VoxCPM2"
provider = "huggingface"
repository = "openbmb/VoxCPM2"
revision = "32279effe8c19989596f05d353d1447f51d9e915"
license = "apache-2.0"
```

Run from the workspace root using a separate Conda environment. Do not install
the model's PyTorch/Gradio dependencies into the pipeline control environment:

```bash
conda create -n voxcpm2 python=3.11
conda run -n voxcpm2 python -m pip install -e ./external/VoxCPM -e .
```

The adapter imports model dependencies lazily, loads only the local model path,
and disables the optional denoiser and text normalizer to avoid additional model
downloads. GPU inference requires a working driver and a compatible PyTorch
installation. Use `--device cuda` to fail explicitly if CUDA is unavailable;
`auto` allows upstream fallback, including potentially slow CPU inference.

## Design a new voice

```bash
conda run --no-capture-output -n voxcpm2 python -m lessons_in_cast_core.voice_design \
  --model-id voxcpm2 \
  --instruction "An adult woman with a bright, high-pitched voice, natural restrained delivery" \
  --text "Good morning. I was wondering when you would wake up." \
  --seed 42 \
  --device cuda \
  --output build/auditions/voxcpm2/ami-design-01.wav
```

The installed entry point `lessons-in-cast-voice-design` exposes the same CLI.
`--root` selects another workspace; all relative audio paths resolve against
that root, not against the model directory. Existing outputs are never replaced;
use a new filename for each variation.

## Apply delivery guidance to a reference voice

```bash
conda run --no-capture-output -n voxcpm2 python -m lessons_in_cast_core.voice_design \
  --model-id voxcpm2 \
  --reference-audio build/auditions/voxcpm2/ami-design-01.wav \
  --instruction "Speak softly, calm and conversational, without excitement" \
  --text "You do not have to worry about me." \
  --seed 42 \
  --device cuda \
  --output build/auditions/voxcpm2/ami-soft-01.wav
```

VoxCPM2 uses reference-conditioned **style control**, aiming to preserve the
reference timbre; this is not a guarantee of arbitrary reference-timbre editing.
No reference transcript is required in this mode. The adapter compiles the
instruction into the upstream `(instruction)Spoken text` syntax and sends the
reference through `reference_wav_path`, not the audio-continuation input.

Designing unrelated scripts from the same description and seed does not guarantee
one stable speaker identity. After selecting a design, use its audio as the
reference for additional utterances. Listen to all results before selecting the
five or more reference utterances required for a character.

## Controls and artifacts

| Option | Default | Meaning |
| --- | --- | --- |
| `--seed` | `42` | Explicit random seed; hardware/software changes can still affect results. |
| `--cfg-value` | `2.0` | Classifier-free guidance scale; stronger guidance is not necessarily better. |
| `--inference-timesteps` | `10` | Diffusion inference steps; more steps cost more compute. |
| `--max-length` | `4096` | Upstream generated-token limit, not an audio duration in seconds. |
| `--device` | `auto` | Upstream device selection, e.g. `cuda`, `cuda:0`, or `cpu`. |
| `--optimize` | off | Enable upstream compilation and model warm-up. |
| `--retry-badcase` | off | Enable upstream automatic retries for suspected bad generations. |

Each audition creates a mono PCM-16 WAV at the model's native sample rate
(48 kHz for VoxCPM2), plus a same-stem JSON sidecar. The sidecar records the input
script, instruction, compiled model text, reference path/hash, seed, inference
settings, model registry metadata, installed VoxCPM version, and output hash.
WAV is intentional for reference assets; production game patches still use the
existing compressed-audio packaging pipeline. These are provenance records,
not an automatic cache or a guarantee of bit-identical reproduction.

Auditions stay under ignored `build/auditions/`. Once approved, preserve selected
audio and its sidecar in the relevant profile's ignored `assets/` directory.
This module does not modify character-to-profile assignments automatically.

Python callers can reuse one `VoxCPM2VoiceDesigner` instance for multiple
sequential `generate(request, output_path)` calls and call `close()` afterwards.
Run those calls inside the backend environment; importing the public contract
from the lightweight control environment does not require PyTorch.
