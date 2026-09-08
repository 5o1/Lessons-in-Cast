# Character auditions

`auditions/` contains reusable **casting projects**, not generated audio.
The core implementation is `lessons_in_cast_core.audition`. Generated sessions,
context collections, takes, adaptations and listening notes live under
`build/auditions/` and are not tracked. Approved references still belong in a
profile's ignored `assets/` directory; casting does not promote them automatically.

## Casting workflow

1. **Prepare the role.** Write a stable vocal brief and identify changes in the
   character's relationships and strategies across the available story. Do not
   equate a chapter, emotion label, or narrator judgment with a fixed voice.
2. **Prepare sides.** Select source-backed excerpts that expose distinct acting
   challenges. A side records the raw source text, short background, addressee,
   intention, emotional state, acting direction, and what the listener should
   hear or avoid. There is no fixed case count or quota per emotion.
3. **Clean, then polish.** Cleaning handles unreadable text, irregular punctuation
   and pauses in long sentences. A separate independent Codex polish pass uses
   context/director notes to add semantic emotion labels and acting controls.
   Validate both stages before synthesis; casting projects contain no rendering labels.
4. **First reading.** Run the same validated sides through one candidate profile/reference
   combination. Keep one recognizable vocal identity across the role's range.
5. **Listen and shortlist.** Judge character fit, intention, intelligibility,
   relaxed diction and usable dynamics. Render success is not acting success.
6. **Callback.** Re-run selected cases with another candidate or a temporary
   reference. A new run name preserves the earlier takes. Make an explicit
   shortlist/callback/reject decision; no automatic ranking or profile promotion.

### Collect the full story, not the active demo

```bash
python -m lessons_in_cast_core.audition collect \
  --character a --speaker q \
  --dialogue build/current/dialogue.tab \
  --collection ami-all-story-contexts
```

This reads all files present in the supplied game-backend export without the
demo/Chapter 1 filter. Omit `--dialogue` to invoke the configured game backend's
extractor first. Use a fresh collection name; existing collections are preserved.
Native extraction may create its usual export in the game release before the
backend copies it into `build/`.

The collector retains entire backend label contexts, including other speakers,
and flags exact speaker hits, additional aliases and name mentions for review.
`--speaker q` means **include unknown-speaker contexts for review**, not "q is
always Ami." An export's file count is not proof of complete story coverage.
Deleted scenes, branches, dreams and impersonation require explicit reading.
The current Ren'Py export does not carry the complete branch/control-flow graph;
read source scripts whenever that distinction affects a side's interpretation.

Use [the side-selection brief](../prompts/audition_side_selection.md) in a separate
Codex session. Semantic selection is deliberately not replaced by a keyword or
emotion classifier, and no paid LLM API is invoked by this module.

### Persistent project format

See [Ami's project](ami/project.json). Its `coverage.status` remains `partial`:
17 initial sides include direct passages from `script.rpy`, `ch2script.rpy`,
`chap3.rpy`, `chap4.rpy`, `chap4part2.rpy`, and `AmiEvents.rpy`. The full-export
collection contains 55 script files; this does not mean every context was read.

Each case keeps a complete canonical `DialogueRecord` under `source`, including
the original text, file, line, label, scene and stable ID. Version 2 intentionally
rejects case-level `text`, `emotion`, `intensity` and `performance`: cleaned text
belongs to cleaning, acting labels to polish, and numerical emotion controls to
the backend. `state` and `direction` are natural-language director
guidance, not machine presets. Original dialogue remains intact for comparison.

Files and comments are English. Source quotations remain in their source
language. Keep full exports and bulk context packets out of this directory.

### Validate and record an audition

```bash
python -m lessons_in_cast_core.audition validate auditions/ami/project.json

python -m lessons_in_cast_core.audition prepare auditions/ami/project.json \
  --dialogue build/current/dialogue.tab --run ami-cleaning
```

Give `build/auditions/ami-cleaning/codex/task.md` to an independent Codex thread.
It reads the normal configured cleanup prompt and `inbox.json`, writes
`outbox.json`, then repeats `cleaning-import` and `cleaning-next` using the commands
in that task. Cleaning sees source context; acting-specific `director_notes` are
retained for the subsequent polish packet rather than injected into cleaning.
No model API is called automatically and no default-neutral annotations are created.

The cleaning run caches `raw.jsonl`, `annotation_requests.jsonl`,
`annotation_responses.jsonl`, the Codex exchange, provenance metadata, and formal
validation outputs. Project, prompt or annotation-config changes require a new
cleaning run. Multiple candidates can reuse the same accepted annotations.

After the independent cleaning workflow has finished, prepare polish:

```bash
python -m lessons_in_cast_core.audition polish-prepare \
  --cleaning build/auditions/ami-cleaning
```

Give `build/auditions/ami-cleaning/polish/codex/task.md` to an independent Codex
thread. It uses `polish-import` / `polish-next`. Polish preserves cleaned words
and pause cues exactly; it cannot silently redo cleaning. Its requests, responses
and validated results are separately cached under `polish/`.

After polish is complete:

```bash
python -m lessons_in_cast_core.audition render auditions/ami/project.json \
  --cleaning build/auditions/ami-cleaning \
  --run ami-first-reading --candidate "Current Ami profile"

python -m lessons_in_cast_core.audition render auditions/ami/project.json \
  --cleaning build/auditions/ami-cleaning \
  --run ami-synthetic-callback --candidate "Synthetic reference callback" \
  --case cute-appeal --case breakdown --case tearful-recovery \
  --reference-audio build/auditions/ami-synthetic-reference-v1/references/synthetic-full.wav
```

`lessons-in-cast-audition` is the equivalent installed entry point. Run the
control CLI in the project's Conda environment; each profile retains its own
backend environment. `--root` precedes the subcommand when specifying a workspace.
`--profile profiles/.../pipeline.py` can audition another explicit candidate.
Otherwise the character's global default profile is used for the whole suite,
not different contextual profiles per case. This preserves the meaning of a
single candidate's range test. No seed or backend settings are secretly changed.

Rendering re-runs the normal annotation validator and uses `SynthesisPlanner`.
Missing, retryable or review-required results stop the selected audition before
model loading. An accepted `omit` produces no take. Effects-only and speech-with-effects
actions currently fail explicitly rather than silently dropping their effects.

Reference overrides go through `VoicePipeline.override_reference_audio` before
preparation. IndexTTS implements this as an instance-local change; unsupported
profiles fail explicitly, rather than ignore the requested override. It accepts
a ready reference file, not a sample directory. Use the existing reference
builder first if preprocessing is needed.

Every session writes:

- `inputs.json`: project snapshot, candidate, effective profile configuration,
  reference hashes and code/config fingerprints.
- `takes/<case>.wav`: individual PCM audition takes, not game release packaging.
- `takes/<case>.job.json` and `.adaptation.json`: requested direction and actual
  backend lowering, including lost or approximated features.
- `manifest.json`: incremental completion, durations and hashes for safe resumption.
- `README.md`: listening sides with context and audio links.
- `casting_notes.json`: manual decisions and notes, initially undecided.

Background, role brief and intention are input to polish, not directly
copied into TTS controls or prepended to the words that the model reads.
Polish produces a single backend-neutral semantic label for each span, including
complex labels such as `tearful_resolve`. Only the IndexTTS adapter maps the label
to its complete eight-axis vector, including normalization;
unknown labels raise an error rather than silently falling back to calm.
New requests use schema 4: cleaning outputs plain text and pauses; polish adds
paired labels without intensity attributes. See [inline speech controls](../docs/inline-speech.md).
Voice changes resolve dynamically against the candidate profile's reference
directory, including when `--reference-audio` overrides that directory.
The current IndexTTS adapter drops free-form direction and cannot guarantee a
crying/recovering blend or strategic sweetness. Its adaptation files say so.
The mapping remains an approximation, not a guarantee of acting quality.

The earlier `ami-first-reading-v1` and `ami-synthetic-callback-v1` sessions used
hand-authored rendering labels and bypassed semantic cleaning. Their audio is
preserved as legacy experiments, not evidence of the corrected full workflow.

Resume with exactly the same inputs and run name. Changed configuration,
reference, code or case selection requires a new run. Modified/unverified audio
is not silently reused. A `.render.lock` prevents simultaneous writers; after a
hard crash, verify that no process is running before removing a stale lock.

### Listening decisions

```bash
python -m lessons_in_cast_core.audition review \
  --run ami-first-reading --case tearful-recovery --decision callback \
  --notes "The identity fits; retry with less sobbing and a clearer recovery beat."
```

These are human casting notes, not ASR scores or legal clearance. A synthesized
reference retains its source provenance. Nothing here asserts that re-synthesis
removes rights constraints or that changing a prompt creates a new voice identity.
