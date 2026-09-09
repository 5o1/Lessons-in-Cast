# LLM execution for cleaning and polish

Status: core implementation complete; real-provider compatibility and listening evaluation still require a configured endpoint. See [operating instructions](annotation-api.md) for the implemented configuration and recovery behavior. This document records the design rationale.

Cleaning and polish independently select the Codex file workflow or an OpenAI-compatible Chat Completions API. Both backends share stage contracts, story material, and validation. API execution manages its context explicitly and supports recovery.

## Constraints identified before implementation

- `DialogueRecord` already carries `filename`, `label`, `scene`, and `line_number`.
- `DialogueBatchBuilder` groups by file and uses fixed windows; it does not enforce label or scene boundaries.
- Without a source-record index, `DialogueBatch.from_dict()` previously dropped label and scene. Both polish and retry use this path; round-tripping is now fixed.
- The Ren'Py context index previously captured only the first scene token and could inherit a scene from a previous label. It now preserves literal image names, resets at labels, and exposes the scene-statement location for snapshots.
- Requests already supported `director_notes`; production and auditions now also snapshot the root `kantoku/` configuration. Auditions retain their individual notes and independent-side contexts.
- Cleaning v4 prepares speakable text, pauses, and actions/effects. Polish v3 assigns emotions, voices, and performance without rewriting accepted cleaning.
- Reuse the existing schema, `AnnotationValidator`, request hashes, retries, and atomic file operations. Codex task/outbox operating instructions do not belong in API prompts.

## 1. Execution units and boundaries

An execution turn contains consecutive dialogue from one stage and one continuous story segment. It can contain several lines but cannot cross a file, label, or explicit scene-instance boundary. Splitting turns never changes dialogue identities.

Prepare boundary-aware requests usable by either backend. If a request still exceeds an API budget, split it into child turns, record the parent batch and target mappings, and merge results back into the original request shape.

Preserve surrounding dialogue and interleaved speakers, including characters that are not synthesis targets.

| Event | Director guidance | Working memory |
| --- | --- | --- |
| Enter file | Load its Kantoku configuration | Start a new session; do not inherit generated memory from another file |
| Enter label | Recompute file → label | Reset transient story and character state unless continuity is explicitly declared |
| Enter scene instance | Recompute file → label → scene | Reset scene-local information; continuous dialogue within the label can retain character state with an explicit scene-change marker |
| Next turn in scene | Reuse the active guidance snapshot | Retain bounded memory and recent source dialogue |
| Retry | Restore guidance and memory from before the original turn | Never use later generated memory to reinterpret an earlier failed turn |

Recompute effective configuration from its parents rather than updating the previous scene's result. Otherwise, expired scene instructions leak into subsequent scenes.

Each Chat Completions request resends its effective context. Entry-time injection means local scope resolution and context replacement, not an assumption that the server remembers an earlier system message.

A Ren'Py `scene` statement changes visuals; it does not necessarily reset the story or emotion. Initially identify repeated visual scenes by their statement location within the label. Mark expressions that cannot be reliably resolved as unknown. Kantoku may define story scenes using explicit source ranges and override visual segmentation. Do not build a complete Ren'Py control-flow interpreter.

Adjacent labels in a source file are not necessarily consecutive at runtime. Cross-label continuity must be declared explicitly.

## 2. Kantoku configuration and prompt injection

Each TOML file under the root `kantoku/` directory uses `name` to match a normalized relative source path, such as `game/AmiEvents.rpy`. Do not match ambiguous basenames. Preserve the README's name → label → scene hierarchy.

This example illustrates configuration structure, not actual game events:

```toml
name = "game/AmiEvents.rpy"

[prompts]
background = "Background needed to understand this file."

[characters.a]
state = "Habitually conceals anxiety."
acting = "Consider what she wants the listener to believe before assigning an outward emotion."

[[labels]]
name = "example_reconciliation"

[labels.prompts]
background = "This exchange follows an argument."

[labels.characters.a]
state = "Still hurt, but trying to rebuild trust."
acting = "Do not start at a breakdown or return to cheerfulness too early."

[[labels.scenes]]
name = "example_room"
start_line = 120
end_line = 180

[labels.scenes.characters.a]
acting = "The words are positive, but the voice remains restrained. Relax only after an explicit turning point."
```

Merge rules are deterministic:

- Update the `prompts` dictionary from general to specific. A matching field replaces its inherited value; an empty string explicitly clears it.
- Merge `characters` by character ID, then update that character's fields. Overriding acting does not erase state.
- Keep rendering parameters in a separate `render` dictionary. Apply scoped overrides to upstream defaults without asking the model to return profile paths or TTS parameters.
- Record each field's source file, scope, and hash. Reject duplicate file mappings, equally specific overlapping ranges, unknown characters, and unsupported parameters.
- Treat audition notes as upstream human guidance. Matching Kantoku fields override them, preserving Kantoku's downstream precedence.

During prepare, before cleaning, resolve and snapshot guidance. Polish inherits that snapshot. Changes to Kantoku require a fresh preparation of the affected run, preventing silent changes of direction between stages.

Keep target guidance separate from guidance belonging to context records. A following scene's direction must not become the current target's direction.

Cleaning receives background, identity, and instructions needed to understand text; it does not produce emotional performance. Polish receives full acting guidance. Human direction cannot override stage invariants, target identities, or the output schema.

## 3. Three context layers

| Layer | Contents | Lifetime and authority |
| --- | --- | --- |
| Human guidance | Stage rules, effective Kantoku, character information, available emotions and voices | Fixed or refreshed by scope; the model cannot modify it |
| Working memory | Story facts, character knowledge, intentions, internal state versus outward delivery, unresolved conflict | Model proposes updates; the program validates and commits them, with evidence and scope |
| Source window | Recent dialogue, current targets, limited lookahead, original text and accepted cleaning for polish | Preserve dialogue order and speakers; never truncate target text |

Polish memory should contain more than `a = sad`. A useful state card looks like:

```text
Character a
Objective: Preserve the relationship with the listener.
Internal state: Anxious; this is an acting hypothesis, not an objective fact.
Outward delivery: Trying to sound light; has not openly expressed resentment.
Latest change: Delivery tightens after the listener avoids answering.
Evidence: id-101, id-106.
Unresolved: Insufficient evidence to distinguish sarcasm from a tentative question.
```

Memory entries contain `character_id`, `kind` (`fact`, `acting_hypothesis`, or `unresolved`), `text`, and `evidence_ids`. The program owns scope and records it on the containing turn commit. An empty character ID denotes scene-local memory. Store useful, traceable conclusions rather than lengthy model reasoning.

The purpose is emotional continuity, not forcing the next line to reuse the previous label.

Memory update rules:

1. A successful turn proposes annotations and bounded memory together. Do not add a separate summarization call to every packet.
2. Commit output and memory only after structural, identity, and stage-semantic validation.
3. Lines marked `review_required` may contribute unresolved entries, not established performance conclusions.
4. Evidence must reference already processed source IDs. Lookahead can clarify irony or a response relationship, but cannot enter memory as an event that has already happened.
5. Prefer source text and human guidance over conflicting generated memory. Remove or downgrade conflicting entries. Valid evidence IDs do not prove a claim is true.
6. Retain current characters, unresolved matters, and necessary recent changes. Archive older entries without feeding an entire chapter of summaries back into the model.

Cleaning and polish have independent working memory. Polish builds its interpretation from accepted cleaning and original dialogue, not cleaning's provisional guesses. Mixed backends exchange standard stage artifacts rather than hidden provider sessions.

## 4. What the API receives

Build messages in this order. Source dialogue and model memory remain lower-authority data rather than system instructions. Prefer ordinary system/user/assistant messages supported by the compatible protocol.

```text
SYSTEM
  Shared task contract, instruction/data boundaries, and output contract.
  Stage-specific cleaning or polish rules.

SYSTEM
  Effective human director guidance with explicit scope.
  Current characters and real available voice names.
  For polish: emotion definitions and examples.

USER
  [Position] file / label / scene instance / turn
  [Working state] Validated state cards, explicitly marked as fallible model memory.
  [Previous dialogue: read-only]
    C001 | Sensei | ...
    C002 | Ami    | ...
  [Current dialogue]
    T001 | Ami    | I'm fine.
    C003 | Sensei | ...  (interleaved context-only speaker)
    T002 | Ami    | Really.
  [Lookahead: read-only; not yet occurred]
    C004 | Sensei | ...
  [Immutable cleaning for polish]
    T001: action=speak; effects=[]; pause(offset=8, seconds=0.3)
    Show original and cleaned text separately when they differ.
  [Task] Return only T001 and T002. Identify meaningful delivery changes and ambiguity.
```

The program maps local T/C identifiers to canonical IDs. Matching strings inside dialogue cannot create targets. Escape and delimit each source record; validate and escape speaker/ID metadata too.

Compact IDs only affect presentation. Cue offsets still refer to decoded speech, not the rendered prompt. Use readable scripts and state cards as input and JSON as output; they need not share a representation.

Extract stage semantics into backend-neutral prompt text. Codex adds its task/inbox/outbox operating instructions; API adds its response protocol. Do not adapt the entire Codex prompt through ad hoc string replacement.

Before calling the model, query the existing profile API for voice tags and inject their actual names. The model needs no filesystem access and cannot invent voice assets.

## 5. Budgets and compaction

Budget system instructions, guidance, memory, dialogue, schema, output allowance, and repair feedback together. Counting dialogue alone is insufficient.

Each stage can configure its context window, output allowance, memory budget, and surrounding line counts. Give polish more context initially.

When a request exceeds the budget:

1. Remove duplicated source excerpts and unnecessary metadata.
2. Remove irrelevant or expired memory while retaining current character transitions and unresolved conflicts.
3. Trim the most distant context, preserving nearby exchanges and interleaved responses.
4. Reduce the number of targets while preserving each line, cleaning bindings, and active guidance intact.
5. Fail explicitly if a single line and its required instructions still do not fit. Never silently truncate source text.

Within a scene, continuity relies on bounded state cards and source windows rather than replaying all previous annotation JSON. Keep fixed prefixes stable where practical, but correctness must not depend on request-cache hits.

The implementation conservatively counts serialized UTF-8 bytes as tokens and reserves correction space. This is not an exact tokenizer; a provider-specific tokenizer can replace it if wasted context becomes material. On a server context-limit error, split the request rather than retrying it unchanged. Verify how the selected service accounts for reasoning tokens within its completion allowance.

## 6. A bounded agent loop and structured output

The agent is a recoverable local state machine: prepare context → call model → validate → repair if needed → commit. It does not require multiple agents talking to one another or arbitrary shell, filesystem, or web tools.

A normal turn uses one LLM call and returns this envelope:

```json
{
  "turn_id": "program-assigned-id",
  "annotations": [],
  "memory": []
}
```

Array elements follow the stage-specific schema. Empty arrays above illustrate only the envelope, not a valid completion.

Map annotation IDs and convert fields losslessly into the existing internal format. Archive memory separately; it does not enter TTS.

Separate the API wire schema from the internal annotation schema. Default to `response_format.type = json_schema`, with `strict = true` inside the `json_schema` object. OpenAI strict schemas require closed objects and all properties to be required; represent optional values using null. A service supporting only JSON mode can explicitly select `json_object`, with the same local validation and no silent fallback. See the [official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

The existing schema cannot be submitted unchanged: polish has a free-key `delivery` dictionary and optional `keyframe_effects`. Represent delivery as an array of fixed `{key, value}` objects on the wire, verify unique keys, and restore the dictionary. Represent optional fields as nullable and omit them during normalization where required by the internal contract.

Validate numeric ranges, uniqueness, and text invariants locally. If a service does not support a schema keyword, relax only the wire schema, not the local contract.

Validation order:

1. HTTP status, refusal, finish reason, truncation, JSON parsing, and wire schema.
2. Turn identity and target set/order; reject missing, duplicate, context-only, or unknown IDs.
3. Existing annotation validation: actions, pauses, emotion markup, keyframes, and cleaning invariants; validate voice names against the supplied assets as well.
4. Memory size, scope, characters, and evidence IDs. The model cannot alter its scope or director configuration.

Repair only the current turn, with specific IDs, error codes, and immutable text rather than a vague retry instruction. Preserve its complete context and enforce a repair-attempt limit. Do not update memory or advance the cursor before a valid result.

On exhaustion, retain failure artifacts and stop the continuous session. Do not skip a failed turn and contaminate later state. Independent sessions can run separately. Human-review decisions remain review decisions; repeated model calls must not wash them into accepted results.

Bounded backoff for rate limits and temporary service failures is separate from semantic repair. Fail immediately on authentication errors or unsupported request parameters.

## 7. Recovery, provenance, and mixed backends

Save an atomic commit record for every turn containing:

- Original request, child-turn mapping, target identities, and stage.
- Model and non-secret API settings, prompt/schema/context-policy versions, and Kantoku snapshot hash.
- Memory before the turn, actual request messages, raw response, validation/repair records, and memory after the turn.
- Usage when reported, lookahead range, trimming decisions, and completion status.

One commit owns both the response and memory-after state. Derive standard `annotation_responses.jsonl` from these commits, avoiding half-commits where annotations are saved but memory is lost.

On resume, verify fingerprints and the last continuous commit before rebuilding messages. Completed turns are not billed again. Read API keys only from configured environment variables; never put their values in fingerprints, logs, or error bodies.

Changes to a model, guidance, or upstream response invalidate dependent subsequent turns. Initially require a fresh run rather than mixing results from different contexts.

Codex continues to export materials for an independent thread to fill and import. API advances through the bounded loop. Both share story material and the final validation gate without requiring Codex to simulate API memory internals.

`run-production` can continue consuming external responses for both stages. Backend selection must also have an actual annotation execution command; configuration loading alone is insufficient.

## 8. Proposed pipeline.toml shape

These fields are implemented. Existing `[codex]` fields retain the shared source filter and prompt paths for compatibility. The production file includes both stage tables with Codex defaults and empty API endpoint/model values.

```toml
[cleaning]
backend = "codex"                         # codex | api

[cleaning.api]
base_url = "https://YOUR-ENDPOINT/v1"
model = "YOUR-CLEANING-MODEL"
api_key_environment = "CLEANING_API_KEY"
response_format = "json_schema"           # json_schema | json_object
context_window_tokens = 32768             # Match the actual model
max_completion_tokens = 8192
max_repair_attempts = 2
timeout_seconds = 180

[cleaning.context]
recent_lines = 12
lookahead_lines = 8
memory_tokens = 1500

[polish]
backend = "api"

[polish.api]
base_url = "https://YOUR-ENDPOINT/v1"
model = "YOUR-POLISH-MODEL"
api_key_environment = "POLISH_API_KEY"
response_format = "json_schema"
context_window_tokens = 65536
max_completion_tokens = 16384
max_repair_attempts = 2
timeout_seconds = 180

[polish.context]
recent_lines = 24
lookahead_lines = 12
memory_tokens = 3000

[kantoku]
directory = "kantoku"
```

Numbers are initial budget examples, not claims about any service's capabilities. Keep both production defaults on Codex. Require API URL, model, and credentials only when API execution is selected.

Handle service differences explicitly in transport, such as a service accepting only `max_tokens`; do not expose an unlimited collection of arbitrary request parameters throughout stage configuration.

Each stage reads its own context settings and credentials. Support all four combinations: codex/api, api/codex, api/api, and codex/codex.

## 9. Implementation and acceptance

1. Implemented label/scene round-tripping and lexical boundaries, including repeated visual scenes and missing scene context.
2. Implemented Kantoku resolution and preparation snapshots. Production rendering overrides route directly to the planner; audition candidates retain their explicit rendering workflow.
3. Implemented shared semantic prompts, boundary-aware turns, and inspectable message previews.
4. Implemented bounded memory, wire-schema normalization, API execution, independent stage configuration, and CLI dispatch.
5. Automated checks cover simulated responses, repair, recovery, transitions, guidance precedence, configuration combinations, and transport construction.
6. Real endpoint compatibility and acting quality remain to be evaluated on a small sample before a paid chapter run.

Acceptance material should cover concealment → uncertainty → release, contradiction between words and delivery, repeated backgrounds at different story moments, label transitions, missing context requiring review, and polish invariants involving pauses/keyframes.

Compare fixed windows against director guidance plus working memory on the same samples. Retain annotation comparisons and synthesized listening results. Structural acceptance and repair rates measure execution reliability. Emotional continuity, turning-point placement, and fidelity to direction require listening judgments; valid JSON is not a substitute.

The first implementation does not need a vector database, automatic discovery of the game's entire story graph, or an additional persistent summarization model. Dialogue identities, explicit scopes, source windows, and evidence-backed state memory cover this request.
