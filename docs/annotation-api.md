# Configurable annotation backends

Cleaning and polish independently select `codex` or `api` in `configs/pipeline.toml`. Both default to the MiniMax Plan API (`MiniMax-M2.7-highspeed`) using `MINIMAX_API_KEY`. API execution uses OpenAI-compatible Chat Completions and the same English stage prompts and local annotation validators as the file workflow. API turns combine scene scopes inside one label while retaining scoped Kantoku guidance; the configured batch size and character budget bound each request.

## Configuration

Edit the existing sections; do not append duplicate TOML tables:

```toml
[cleaning]
backend = "codex"

[polish]
backend = "api"

[polish.api]
base_url = "https://YOUR-ENDPOINT/v1"
model = "YOUR-MODEL"
api_key_environment = "POLISH_API_KEY"
response_format = "json_schema"
context_window_tokens = 65536
max_completion_tokens = 16384
completion_token_parameter = "max_completion_tokens"
max_repair_attempts = 2
timeout_seconds = 180
parallel_workers = 4

[polish.context]
recent_lines = 24
lookahead_lines = 12
memory_tokens = 3000
```

Set the named key environment variable in your shell. Keys are not stored in TOML or checkpoints. Each stage can use a different provider, model, and key. `base_url` excludes `/chat/completions`; the client appends that path. Configure the final endpoint because redirects are rejected.

Use `completion_token_parameter = "max_tokens"` when required by a compatible service. `response_format = "json_object"` is available for services without strict JSON Schema support; it still uses the same local structural and semantic checks. The MiniMax defaults use `json_object`, `max_tokens`, and `reasoning_split = true` to keep reasoning out of the JSON response. Omit `reasoning_split` for providers that do not support it. Unsupported protocol settings never cause a silent fallback.

Match the budgets to the actual model. The initial estimator counts serialized UTF-8 bytes conservatively as tokens, with space reserved for output and correction feedback. This is deliberately conservative, not a precise tokenizer. Context is trimmed before targets are split; a single target that cannot fit fails explicitly. Output truncation or provider context-limit errors split multi-target turns without discarding any target text.

On validation failure, the next request includes the failed assistant output and the local error report. If that combination would exceed the context budget, it sends the error report with the original request and asks for a complete replacement. Invalid or oversized working-memory entries are safely discarded locally because they do not change dialogue annotations. `max_repair_attempts` bounds model corrections, and every replacement passes the same validators. A complete Markdown JSON fence is unwrapped without changing its contents; surrounding prose remains invalid.

The existing `[codex].source_files` remains the production annotation source filter for both backends. Auditions use their selected cases instead. `[codex].prompt_path` and `polish_prompt_path` remain shared prompt paths for compatibility; their contents now hold stage semantics, while operating instructions are supplied by the chosen backend.

## Commands

From the repository root:

```bash
PYTHONPATH=src python3 -m lessons_in_cast_core prepare --input /path/to/dialogue.tab
PYTHONPATH=src python3 -m lessons_in_cast_core annotate --stage cleaning
# For Codex, complete the exported task and import its output first.
PYTHONPATH=src python3 -m lessons_in_cast_core validate
PYTHONPATH=src python3 -m lessons_in_cast_core polish-prepare
PYTHONPATH=src python3 -m lessons_in_cast_core annotate --stage polish
PYTHONPATH=src python3 -m lessons_in_cast_core polish-validate
PYTHONPATH=src python3 -m lessons_in_cast_core plan-tts
```

`annotate` exports the next Codex packet or executes all pending API turns, depending on the selected stage. Existing `codex-next`, `codex-import`, and `codex-status` remain explicit file-workflow commands. Preparation never starts a paid API call.

For an API stage, inspect the first pending request without credentials or a network call:

```bash
PYTHONPATH=src python3 -m lessons_in_cast_core annotate --stage polish --preview
```

The report points to `api/initial/preview.jsonl` under the selected stage directory. It contains the actual script-style messages, target mapping, output schema, trimming report, and input estimate. If all turns are already committed, there is no pending preview to write.

Use `--retry` with `annotate` for validator-generated retry requests. Ordinary API transport or validation failures are resumed by rerunning the same command: committed turns are replayed locally and the failed turn is attempted again. Review-required results remain review-required; polish preparation and synthesis retain their existing acceptance gates.

Polish validation applies an optional run-local `polish_overrides.toml` beside the run's `polish/` directory. It uses the same stable dialogue-ID format and validation rules as cleaning overrides, so the production synthesis gate sees the same reviewed result as the standalone `polish-validate` command.

For auditions, `cleaning-next` and `polish-next` honor the corresponding backend. `polish-prepare` prepares API inputs without calling the service. For production, place the global build option before the command: `--build-dir build/my-run annotate --stage polish`. Use the audition commands for audition runs so production source filtering is not applied. Each audition side starts with independent working memory.

## Context and direction

See [Kantoku configuration](../kantoku/README.md). API turns stay within a file and label. Independent labels run concurrently up to `parallel_workers`; explicit `continuity_from` chains stay serial. Each scene still receives its resolved guidance inside the combined turn. Each request supplies:

- Shared stage rules and effective human director guidance.
- For polish, the emotion catalog and actual voice tags queried from profiles.
- Fallible, evidence-backed working memory.
- Readable dialogue with local target/context identifiers and canonical evidence IDs.
- Read-only previous dialogue, interleaved speakers, and explicitly marked lookahead.
- Immutable accepted cleaning and original text for polish.

Working memory distinguishes facts, acting hypotheses, and unresolved questions. It is generated in the same call as annotations and committed only after validation. Lookahead cannot become a past event in memory. Review lines can contribute only unresolved entries. Memory is independent between cleaning and polish; scope transitions replace expired guidance and reset or retain memory according to the declared continuity.

The model returns structured annotations and bounded replacement memory. It has no shell or filesystem tools. Wire-format delivery entries normalize back to the existing dictionary format; optional keyframes normalize back to the internal convention. Valid JSON never bypasses text, pause, action, emotion, or voice checks.

## Recovery and artifacts

API execution writes under `<stage-root>/api/initial/` or `api/retry/`:

- `run.jsonl`: non-secret configuration and input fingerprints.
- `turn-XXXXXX.jsonl`: atomic accepted commits containing outputs, before/after memory, actual requests/responses, validation attempts, scope, evidence, and a content hash.
- `failed-attempts/`: responses from failed or split turns that did not become accepted commits.
- `failure.jsonl`: the last terminal failure and its target IDs.
- `.lock`: an advisory lock preventing concurrent writers for the same pass.

Standard annotation response JSONL is derived from commits. Successful replay preserves response timestamps so it does not invalidate an already prepared polish stage. An interrupted incomplete batch can resume from its committed child turns. Changed inputs, settings, voice names, prompt, or checkpoints are rejected rather than silently mixed. Use a fresh build directory for changed inputs.

The stage lock uses POSIX `flock`, matching the current Linux workspace. The API does not require a new third-party dependency. No real provider call is made during automated tests.
