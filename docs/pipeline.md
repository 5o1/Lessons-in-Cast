# Pipeline

Lessons in Cast keeps extraction, semantic annotation, validation, synthesis,
and Ren'Py integration as independent, restartable stages.

## Data flow

    Ren'Py release
      -> dialogue.tab
      -> raw.jsonl
      -> model_requests.jsonl
      -> model_responses.jsonl
      -> validated.jsonl
      -> tts_jobs.jsonl + render_tasks.jsonl
      -> voice/*.wav
      -> release_bundle/game/

raw.jsonl is a lossless representation of the six columns emitted by Ren'Py.
No semantic cleaning or source-level control-flow reconstruction occurs before
annotation.

Model requests contain target records plus mechanically adjacent records from
the same source file. They do not claim to represent a runtime scene. One model
response performs both semantic text cleaning and emotion/delivery annotation.
The response JSON Schema is embedded in every request.

All model output is untrusted. The validation gate checks request hashes, batch
and dialogue IDs, complete target coverage, strict fields, action-dependent
rules, configured emotion/effect values, placeholders, tags, control
characters, and suspicious text-length changes. Records become accepted,
review_required, retryable, or rejected. Only accepted records can become TTS
jobs.

Failed targets are exported individually to retry_requests.jsonl. Process those
requests into retry_responses.jsonl, then run retry validation to merge
successful replacements into validated.jsonl.

Initial and retry diagnostics are kept separately in validation_issues.jsonl
and retry_validation_issues.jsonl. The run manifest records extraction inputs,
content hashes, adapter configuration, cache reuse, and stage counts.

Human overrides in configs/overrides.toml are keyed by stable dialogue ID. Set
approved = true to approve a structurally valid warning, or status = "rejected"
to prevent synthesis.

TTS jobs are cached by text, character, emotion, delivery, model paths, backend
configuration, and audio configuration. Ensemble characters generate one job
per configured member and a line-level unison render task. Effects remain on
the render task rather than the character.

Final audio uses Ren'Py dialogue identifiers as filenames. The generated
lessons_in_cast_voice.rpy configures automatic voice lookup as:

    config.auto_voice = "voice/{id}.wav"

The release bundle is produced separately and never mutates the configured
game release.

## Commands

    lessons-in-cast check-config
    lessons-in-cast extract
    lessons-in-cast prepare
    lessons-in-cast annotate-mock
    lessons-in-cast validate
    lessons-in-cast annotate-mock --retry
    lessons-in-cast validate --retry
    lessons-in-cast plan-tts
    lessons-in-cast synthesize-mock
    lessons-in-cast bundle

The mock commands exist only to test the full pipeline. A production annotator
and synthesizer implement the protocols in annotation/api.py and
synthesis/api.py.
