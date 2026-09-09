# Pipeline

Lessons in Cast keeps extraction, semantic annotation, validation, synthesis,
and game integration as independent, restartable stages. All generated
intermediates and build products are contained under build/current/ by default.

Cleaning and polish independently select Codex or an OpenAI-compatible API in
`configs/pipeline.toml`. See [annotation execution](annotation-api.md) for commands,
context management, structured output, and recovery, and [Kantoku](../kantoku/README.md)
for scoped background and acting guidance.

## Data flow

    configured game release (Ren'Py by default)
      -> build/current/dialogue.tab
      -> build/current/raw.jsonl
      -> build/current/annotation_requests.jsonl
      -> build/current/codex/initial/inbox.json
      -> build/current/annotation_responses.jsonl
      -> build/current/validated.jsonl
      -> build/current/polish/annotation_requests.jsonl
      -> build/current/polish/annotation_responses.jsonl
      -> build/current/polish/validated.jsonl
      -> build/current/tts_jobs.jsonl + build/current/render_tasks.jsonl
      -> build/current/synthesis_adaptations.jsonl
      -> build/current/audio/raw/<character>/<cache-key>.wav
      -> build/current/voice/<dialogue-id>.opus
      -> build/current/release_bundle/game/lessons_in_cast_voice.rpa
      -> build/current/release_bundle/game/lessons_in_cast_voice.rpy
      -> build/current/lessons_in_cast_voice_patch.zip

build/current/raw.jsonl is the backend-normalized, lossless dialogue
representation. For Ren'Py, it preserves all six columns emitted by the native
dialogue command and adds the nearest lexical `label` and `scene` found above
each source line. Missing source context emits a warning and remains empty; if
the label is missing, the context path is truncated before the scene. No
semantic cleaning or control-flow reconstruction occurs before annotation.

Character configuration uses the same deterministic context path. The global
`[characters.<id>]` table is followed by optional source-path, label, and scene
tables, with each more specific table inheriting and overriding its parent:

    [characters.crowd2."game/events/chapter/a.rpy".opening.classroom]
    default_voice_profile = "profiles/crowd2_classroom/pipeline.py"

Source paths retain their release-relative directories and use normalized `/`
separators. A missing label stops matching at the source-path table; a missing
scene stops matching at the label table.

Annotation requests contain targets and mechanically adjacent context from the
same source file. Prepared targets split at resolved label/scene boundaries;
these lexical or explicitly configured boundaries do not reconstruct runtime control
flow. The configured backend performs separate text cleaning and acting passes.
The response JSON Schema is embedded in every request.

All Codex output is untrusted. The validation gate checks request hashes, batch
and dialogue IDs, complete target coverage, strict fields, action-dependent
rules, configured emotion/effect values, placeholders, tags, control
characters, and suspicious text-length changes. Records become accepted,
review_required, retryable, or rejected. Only accepted records can become TTS
jobs.

## Galgame backends

The `[galgame]` section of `configs/pipeline.toml` selects a backend by stable
ID; the current default is `renpy`. `GalgameBackend` is the public contract in
`src/lessons_in_cast_core/galgame/api.py`. Each implementation owns extraction,
normalization of its native dialogue export, virtual voice-path construction,
integration-artifact generation, and release-bundle installation. The main
pipeline depends only on this contract.

Ren'Py-specific code lives under `src/lessons_in_cast_core/galgame/renpy/`. To
add another engine, implement `GalgameBackend` in a sibling package and register
its stable ID in `galgame/loader.py`; speech profiles and synthesis backends do
not need to change.

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

    lessons-in-cast prepare --scope amnesia_ami_maya
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

TTS jobs are cached by text, character, emotion, delivery, resolved
voice-profile configuration, and audio configuration. Ensemble characters
generate one job
per configured member and a line-level unison render task. Effects remain on
the render task rather than the character. When a character has no available
profile in its resolved source context, planning emits a
`missing_voice_profile` issue and omits that voice. An ensemble keeps its
available members; a line with no renderable member produces no audio task.

The pronunciation lexicon is also backend-neutral. A spelling can provide
several segment alphabets (for example ARPABET and IPA) plus optional lexical
prosody aligned by syllable, mora, or phoneme. Each aligned unit has its own
0..1 time axis, aligned representations in one or more phoneme alphabets,
duration multiplier, and an arbitrary number of F0 targets in semitones
relative to the phrase-local baseline. The entry
also declares step, linear, or smooth interpolation. This is deliberately more
precise than lexical stress: it can preserve the onset, internal turn, and
release of each unit's pitch movement without fixing a character to one
absolute vocal register.

Backends lower that representation according to their capabilities and record
the result in `synthesis_adaptations.jsonl`. MiniMax receives syllable-aligned
IPA tone letters as a quantized approximation. IndexTTS keeps ARPABET phonemes
and stress but reports the F0 curve and unit timing as lost because its current
inference interface has no word-local pitch control. A backend with phoneme-F0
controls can consume the core targets directly without changing the JSON or
lexicon schema.

The configured backend owns dialogue export parsing, virtual audio paths,
integration artifacts, and release installation. The default Ren'Py backend
uses dialogue identifiers as filenames. The generated
lessons_in_cast_voice.rpy configures automatic voice lookup as:

    config.auto_voice = _lessons_in_cast_auto_voice

The release bundle is produced separately and never mutates the configured
game release.
Each render task carries both an internal build path and an install-time virtual
path. For example, dialogue from game/chapter/main.rpy receives a virtual path
below voice/chapter/main/. Delivery audio is 48 kHz mono Opus and is packed into
game/lessons_in_cast_voice.rpa; individual audio files are not emitted in the
release tree. The generated callable maps each Ren.Py dialogue identifier to its
RPA member path. The sibling lessons_in_cast_voice_patch.zip contains a top-level
game/ directory and can be overlaid onto a Ren.Py release root. Rebuilding
replaces the bundle.s game tree and patch ZIP, so removed audio cannot survive
as a stale file.

IndexTTS 2.5 runs in its own configured Python environment through one
persistent JSON-lines worker per active profile. Large production runs group
jobs by profile rather than story order. Switching to the next profile closes
the previous worker before loading another model, so many character profiles
do not accumulate duplicate model copies in GPU memory. Each profile points to a curated reference below
its local `assets/` directory and records the ordered source filenames used to
build it. Profile assets are ignored by Git and must be provisioned locally.
When the prepared reference is missing, `prepare-voices` deterministically
rebuilds it from those ordered sources with the configured held-open silence
gate. The worker consumes the prepared artifact directly instead of applying
the gate a second time. IndexTTS itself hard-truncates the reference to its
first 15 seconds.

Character rendering is selected by `default_voice_profile`. Public contracts and profile loading live under
`src/lessons_in_cast_core/synthesis/profiles/`; reference preparation lives under
`synthesis/references/`; concrete backend families live under
`synthesis/backends/`. The model-neutral planner, job types, renderer, and backend
protocol remain directly under `synthesis/`. The root `profiles/` directory is the
user-configurable project layer. It supports both single-file entrypoints and
bundles containing `pipeline.py`, configuration, and profile-owned assets.

The active bundle owns its model ID, reference settings, `base_speed`,
pronunciation, language, seed, precision, segmentation, and acoustic-token
generation. Project emotions are mapped to the official eight axes, biased and
capped to a total strength of 0.8 like the official WebUI; neutral uses a zero
vector. The worker also overrides the upstream hard-coded sampling flag so
configured `do_sample=false` actually reaches the token generator. Model IDs are
resolved through `configs/model_sources.toml`; resolved source metadata is part
of the effective profile configuration. Per-dialogue profile selection is
reserved for a future extension and is not part of the
current dialogue schema.

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
    lessons-in-cast prepare-voices
    lessons-in-cast bundle

    lessons-in-cast build-reference --character ch --input-dir SAMPLE_DIRECTORY
    lessons-in-cast synthesize
    lessons-in-cast run-production --input dialogue.tab --responses responses.jsonl

Semantic cleaning remains an independent Codex file workflow;
the production runner only consumes its response JSONL and never invokes Codex.

run-production performs preparation, validation, TTS planning, speech synthesis, audio validation, and installation through the selected galgame backend in one process. By default
it starts from a fresh set of pipeline-owned artifacts and, after success,
retains release_bundle/, lessons_in_cast_voice_patch.zip, and run_manifest.json. Input dialogue and response
files must therefore be outside the selected build directory. Pass
--cache-intermediates while debugging to retain request/validation JSONL, raw
TTS audio, rendered audio, and manifests.
