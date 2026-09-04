# Pipeline

Lessons in Cast keeps extraction, semantic annotation, validation, synthesis,
and Ren'Py integration as independent, restartable stages. All generated
intermediates and build products are contained under build/current/ by default.

## Data flow

    Ren'Py release
      -> build/current/dialogue.tab
      -> build/current/raw.jsonl
      -> build/current/annotation_requests.jsonl
      -> build/current/codex/initial/inbox.json
      -> build/current/annotation_responses.jsonl
      -> build/current/validated.jsonl
      -> build/current/tts_jobs.jsonl + build/current/render_tasks.jsonl
      -> build/current/voice/<dialogue-id>.wav
      -> build/current/release_bundle/game/voice/<source-script>/<dialogue-id>.wav
      -> build/current/release_bundle/game/lessons_in_cast_voice.rpy

build/current/raw.jsonl is a lossless representation of the six columns emitted by Ren'Py.
No semantic cleaning or source-level control-flow reconstruction occurs before
annotation.

Annotation requests contain target records plus mechanically adjacent records
from the same source file. They do not claim to represent a runtime scene. A
dedicated Codex thread performs semantic text cleaning and emotion/delivery
annotation. The response JSON Schema is embedded in every request.

All Codex output is untrusted. The validation gate checks request hashes, batch
and dialogue IDs, complete target coverage, strict fields, action-dependent
rules, configured emotion/effect values, placeholders, tags, control
characters, and suspicious text-length changes. Records become accepted,
review_required, retryable, or rejected. Only accepted records can become TTS
jobs.

## Codex annotation workflow

Codex is used as a continuing file-processing agent, not as a stateless API.
`codex-next` takes the next uninterrupted run of pending batches from one source
file, removes overlapping context records, and exports one chronologically
ordered transcript packet. Records to annotate are marked with `target: true`;
the surrounding records remain read-only context.

The default packet contains two adjacent batches, normally about 100 targets.
This remains configurable as `codex.batches_per_packet`. A packet never crosses
a source-file boundary. Boundary context is still included, so correctness does
not depend solely on conversational memory, while processing every packet in
the same Codex thread lets understanding naturally carry forward through long
conversations.

The current annotation run is scoped by `codex.source_files`. It contains every
dialogue extracted from `game/script.rpy`, the Chapter 1 main-story script.
Packets only divide this dataset into manageable turns; they do not shorten the
configured chapter range.

Prepare the first packet:

    lessons-in-cast prepare
    lessons-in-cast codex-status
    lessons-in-cast codex-next

Then open one independent Codex thread in the repository and instruct it to
read `build/current/codex/initial/task.md` completely and continue processing
packets until no pending batches remain. The generated task gives the exact
inbox, outbox, import, and next-packet commands. Each successful import
atomically adds request hashes, prompt version, prompt hash, workflow version,
and a UTC timestamp to `build/current/annotation_responses.jsonl`. The
character mapping hash is also bound to the workflow configuration. Codex never
has to calculate or edit this provenance.

The cleaning prompt is `prompts/codex_dialogue_cleanup.md`. It requires Codex
to read each packet top to bottom, use continuing thread context, preserve the
original meaning and runtime substitutions, reason about visual-only text and
special effects, and mark ambiguity for review. It expressly forbids replacing
semantic judgment with a mechanical search-and-replace script.

Failed targets are exported individually to build/current/retry_requests.jsonl. Start
the retry pass with `codex-next --retry`, process
`build/current/codex/retry/task.md` in the same manner, and run `validate --retry` after
`codex-status --retry` reports no pending batches. Successful replacements are
merged into build/current/validated.jsonl without reprocessing successful targets.

Initial and retry diagnostics are kept separately in
build/current/validation_issues.jsonl and build/current/retry_validation_issues.jsonl. The run
manifest records extraction inputs, content hashes, adapter configuration,
cache reuse, and stage counts.

Human overrides in configs/overrides.toml are keyed by stable dialogue ID. Set
approved = true to approve a structurally valid warning, or status = "rejected"
to prevent synthesis.

TTS jobs are cached by text, character, emotion, delivery, model paths, backend
configuration, and audio configuration. Ensemble characters generate one job
per configured member and a line-level unison render task. Effects remain on
the render task rather than the character.

Final audio uses Ren'Py dialogue identifiers as filenames. The generated
lessons_in_cast_voice.rpy configures automatic voice lookup as:

    config.auto_voice = _lessons_in_cast_auto_voice

The release bundle is produced separately and never mutates the configured
game release.
Each render task carries both an internal build path and an install-time virtual
path. For example, dialogue from game/chapter/main.rpy is installed below
game/voice/chapter/main/. The generated callable maps each Ren'Py dialogue
identifier to that exact virtual path. Rebuilding replaces the bundle's game
tree, so audio removed from the current plan cannot survive as a stale file.

IndexTTS 2.5 runs in its own configured Python environment through one
persistent JSON-lines worker. Before synthesis, each character pipeline
automatically selects and combines source samples, applies the held-open silence
gate, and writes a generated reference below `build/references/`. A sidecar
manifest binds that reference to source hashes, processing settings, and the
pipeline ID, so unchanged references are reused and changed inputs are rebuilt.
The worker consumes this single prepared artifact directly instead of applying
the silence gate a second time. IndexTTS itself hard-truncates the prepared
reference to its first 15 seconds.

Character rendering is selected by `generation_script_path`. The backend-neutral
`VoicePipeline` interface and reusable backend-family bases live under
`src/lessons_in_cast/synthesis/`. The root `voice_pipelines/` directory is the
game-specific extension layer: each character/backend/strategy combination
lives there in a separate module.

The character pipeline TOML also configures minimum detected speech,
pronunciation, language, seed, precision, segmentation, and acoustic-token
generation. Project
emotions are mapped to the official eight axes, biased and capped to a total
strength of 0.8 like the official WebUI; neutral uses a zero vector. The worker
also overrides the upstream hard-coded sampling flag so configured
`do_sample=false` actually reaches the token generator. Each character has a
required `base_speed` multiplier in `configs/characters.toml`; values above 1.0
are faster, and values below 1.0 are slower.

Use `--build-dir` to select another generated-file root.

## Commands

    lessons-in-cast check-config
    lessons-in-cast extract
    lessons-in-cast prepare
    lessons-in-cast codex-status
    lessons-in-cast codex-next
    lessons-in-cast codex-import
    lessons-in-cast validate
    lessons-in-cast codex-next --retry
    lessons-in-cast codex-import --retry
    lessons-in-cast codex-status --retry
    lessons-in-cast validate --retry
    lessons-in-cast plan-tts
    lessons-in-cast synthesize-mock
    lessons-in-cast prepare-voices
    lessons-in-cast bundle

    lessons-in-cast build-reference --character ch --input-dir SAMPLE_DIRECTORY
    lessons-in-cast synthesize
    lessons-in-cast run-production --input dialogue.tab --responses responses.jsonl
The annotate-mock, synthesize-mock, and run-mock commands exist only for
automated tests. Semantic cleaning remains an independent Codex file workflow;
the production runner only consumes its response JSONL and never invokes Codex.

run-production performs preparation, validation, TTS planning, IndexTTS
synthesis, audio validation, and Ren'Py installation in one process. By default
it starts from a fresh set of pipeline-owned artifacts and, after success,
retains only release_bundle/ and run_manifest.json. Input dialogue and response
files must therefore be outside the selected build directory. Pass
--cache-intermediates while debugging to retain request/validation JSONL, raw
TTS audio, rendered audio, and manifests.
