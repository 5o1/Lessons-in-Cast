# Inline speech controls

The separate polish stage owns semantic emotion and voice selection. Cleaning
prepares readable text, irregular punctuation and pauses in long sentences; it
does not assign acting semantics. A game dialogue
record remains one line/ID even when it contains multiple sentences or changes
delivery. Schema-5 polish `spoken_text` uses paired, backend-neutral markup:

```json
{
  "spoken_text": "<emotion name=\"afraid\">I thought you had left.</emotion> <voice name=\"soft\"><emotion name=\"tearful_resolve\">But you're here. You came back.</emotion></voice>"
}
```

This is a field excerpt, not a complete annotation response. Do not return
top-level emotion/intensity in new responses or an intensity attribute in a tag.
Each span has ONE preset semantic label or an `arbitrary_emotion` description,
never both, and not a combination such as `sad,calm`.
Labels are selected from the request's allowed emotions and definitions. All speech
must be in emotion spans. Voice wrappers are optional and contain emotion spans.
No nested voices, nested emotions, arbitrary HTML or unlabelled speech. Escape
literal ampersands and angle brackets. Tags are never sent as words to TTS.

The validator checks markup and names, then checks text risks and
performance cue offsets against decoded speech without tags. Original tagged
polish output remains cached separately from cleaning. The synthesis planner retains one dialogue job
with plain text and typed segments. Adapters own backend-specific lowering.
Old combined-stage or intensity-bearing artifacts are not inputs to the new
two-stage workflow. Preserve them as history and prepare new requests; do not
mechanically relabel old annotations to claim a new polish pass.

Core label definitions live in `src/lessons_in_cast_core/emotions.py`. The ten
initial complex labels include tearful_resolve, restrained_grief, emotional_breakdown,
tearful_remorse, playful_affection, guarded_composure, firm_boundary,
cheerful_pressure, tentative_hope and possessive_care. Each has a definition and
an example, included in polish packets, alongside the existing basic labels.
IndexTTS maps each label to a full eight-axis vector, potentially with several
nonzero values. Profiles can select an automatically prepared QwenEmotion cache;
the legacy backend `emotions.py` remains the manual mapping when no cache is
configured. Neither automatic nor manual values guarantee calibrated acting.

## Dynamic voice references

Voice names are exact, case-sensitive audio filename stems, not a preset enum:

```text
profiles/a_index_tts/assets/references/
  default.wav
  soft.flac
  tearful.wav
```

`<voice name="soft">` selects `soft.flac`. Outside a voice wrapper, the profile's
configured default reference is used. Closing the wrapper restores the default.
The default filename need not literally be `default.wav`; its parent defines
the lookup directory. A temporary reference override changes that lookup root.

Lookup is non-recursive and ignores non-audio files. Supported extensions are
wav, flac, ogg, opus, mp3, m4a, aac, aif and aiff; decoding still depends on the
backend's installed audio libraries. Missing names, duplicate stems (such as
soft.wav and soft.flac), paths, or symlinks outside the directory are not usable.
There is no silent fallback. Reference inventories and contents participate in
IndexTTS configuration/cache fingerprints. Reference assets remain local/ignored.

Query the public profile contract without preparing references or loading a model:

```python
# profile is an instance returned by load_voice_profile(...).
tags: tuple[str, ...] = profile.list_voice_tags()
```

The result is a dynamically discovered tuple, including the default file's stem
if present. An empty directory returns an empty tuple. Unsupported profiles raise
NotImplementedError; ambiguous filenames raise ValueError. Query does not check
audio quality, synthesize references, or upload files.

```bash
python -m lessons_in_cast_core voice-tags --character a
python -m lessons_in_cast_core voice-tags --character a \
  --profile profiles/a_index_tts/pipeline.py
```

The CLI returns `profile`, `supported` and `tags` as JSON; unsupported profiles
also return a reason. `--reference-audio` queries a temporary override directory.

## Single-emotion backends

IndexTTS merges adjacent spans only when the semantic emotion label and voice match.
Each resulting segment is rendered with its own vector and reference using the
same loaded worker. Cue offsets are rebased; a cue exactly at a boundary belongs
to the following segment, and end-of-line cues belong to the final segment.

PCM segments are concatenated in order without trimming, overlap or additional
fixed silence. The original punctuation/cues control pauses, subject to the
backend's documented approximations. Each segment and job is cached under a
`*.segments/` directory beside its parent WAV. The parent is published atomically
only after all segments succeed. Normal downstream effects/encoding/packaging
still consume one audio file for the original dialogue identifier.

Segmented generation does not guarantee natural joins or constant identity:
different references can change timbre, loudness and recording quality. Listen
to transitions before approving a candidate. The adaptation report records each
segment's effective controls and the concatenation strategy.

## Separate stage workflow

Both passes use the independent Codex file workflow. From an active run:

```bash
python -m lessons_in_cast_core prepare --input path/to/dialogue.tab
python -m lessons_in_cast_core codex-next --stage cleaning
# Complete the cleaning task's import/next loop in an independent thread.
python -m lessons_in_cast_core validate
python -m lessons_in_cast_core polish-prepare
python -m lessons_in_cast_core codex-next --stage polish
# Complete the polish task's import/next loop in an independent thread.
python -m lessons_in_cast_core polish-validate
python -m lessons_in_cast_core plan-tts
python -m lessons_in_cast_core synthesize
```

Use `--build-dir` before the subcommand to select another run. Cleaning artifacts
remain at the run root. Polish has its own `polish/annotation_requests.jsonl`,
`annotation_responses.jsonl`, `validated.jsonl`, retry artifacts and Codex workspace.
The separate prompts are configured via `codex.prompt_path` and
`codex.polish_prompt_path`. Polish cannot alter decoded cleaned text, action,
effects or cleaning pause cues. Changed inputs invalidate the downstream polish
binding; missing or unaccepted polish cannot be synthesized. `run-production`
requires both `--responses` (cleaning) and `--polish-responses`.

MiniMax and GPT-SoVITS use the same segmentation fallback for emotion spans, with
their existing per-segment emotion approximations. Local-reference voice tags
are currently implemented by IndexTTS only. MiniMax uses remote voice IDs;
GPT-SoVITS also needs the matching reference transcript. Both reject unsupported
voice tags before generation instead of pretending to switch references.

## Preset preparation and runtime descriptions

See [Emotion presets and arbitrary emotion](emotion-presets.md) for the registration
and preparation CLI, IndexTTS vector caches, and the schema-5 `arbitrary_emotion`
extension. Arbitrary emotion and preset emotion are mutually exclusive per span.
