# IndexTTS expressive punctuation pauses

Implementation for [issue #5](https://github.com/5o1/Lessons-in-Cast/issues/5) is scoped to the **IndexTTS adapter only**. Core dialogue, cleaned/polished text, emotion labels, shared segment concatenation and other speech backends are unchanged.

In an IndexTTS profile's `config.toml`:

```toml
[backend]
expressive_pause = "period" # default; alternatives: "comma", "native"
```

| Input | `comma` | `period` |
| --- | --- | --- |
| `Stop! Listen!` | `Stop!, Listen!,` | `Stop!. Listen!.` |
| `Why? Really?` | `Why?, Really?,` | `Why?. Really?.` |
| `What?! Really!?` | `What?!, Really!?,` | `What?!. Really!?.` |
| `Stop!!! Why???` | `Stop!, Why?,` | `Stop!. Why?.` |

`native` retains the previous punctuation behavior. The default is an explicit period cue, not a fixed silence duration. The model remains responsible for the realized timing and intonation. Existing commas, periods and ellipses are not duplicated. Explicit core pause cues at an already terminal boundary reuse that boundary instead of adding another ellipsis; this is approximate, not exact duration control. Cue offsets are interpreted before repeated punctuation is normalized. Pronunciation spans are protected.

The user selected `period` after comparing all three modes on demo1's "It's Ami, Sensei! Ami!" (`game/script.rpy:572`). Only the period version was accepted for that probe, so it replaces the provisional comma default. The comparison is cached under `build/auditions/index-tts-ami-sensei-punctuation-v1/`. This selection does not assert listening acceptance of every other question/exclamation case.

The adapter does **not** infer anger from `!`, surprise from `?`, or increase the emotion vector because a mark is repeated. Preset vectors and arbitrary emotion descriptions still come from the existing polish workflow. Punctuation-only speech jobs (`!`, `?`, `?!`) are rejected in the repaired modes: cleaning/polish must supply an intended vocalization or omission, not leave IndexTTS to invent one.

## Investigation and artifacts

The installed IndexTTS 2.5 normalizer was tested directly: single, repeated and mixed `!`/`?` survive normalization. Thus punctuation deletion is not the explanation for these cases. The explicit comma/period is a backend compatibility cue for the audible pause, not a repair to missing source punctuation.

The upstream token-budget splitter can independently create isolated punctuation or split a word at very small budgets (for example, `Stop! Listen to me!` at a five-token budget produces a final `!` segment). That issue is **not claimed fixed** by this marker change. The upstream implementation and token splitting remain unchanged; do not reduce the normal token budget merely to force pauses.

`*.adaptation.json` shows the compiled punctuation and selected mode. Each generated component also saves `*.frontend.json`, including normalized text, actual token segments, token counts and the worker's inter-chunk silence setting. The adapter configuration includes the mode and a frontend version so ordinary pipeline cache keys change with this behavior. Existing audition files are never overwritten to disguise a change of inputs.

Inline emotion takes still use the existing complete-PCM concatenation. There is **no new endpoint trimming or standardized silence replacement** in this fix. Native end/start silence can accumulate at those joins; IndexTTS's own token chunks may additionally use `interval_silence_ms`. Neither mechanism should be confused with the text punctuation cue.

## Comparison audition

```bash
PYTHONPATH=src python scripts/run_index_tts_punctuation_auditions.py --run index-tts-punctuation-v1
```

Runs one persistent local worker, the existing Ami reference and fixed seed, comparing `native`, `comma`, and `period` on three probes. Happy/angry probes reuse previously accepted audition jobs. The mixed-question probe cites its game source and deliberately uses neutral emotion as a controlled test condition, not a new polish prediction. All nine WAVs, input/adaptation records and the manifest are under `build/auditions/RUN/`. Use a new run name for each experiment.

Listen for audible phrase boundaries, retained question/exclamation intonation, extra hesitation and trailing silence. Technical checks prove that the markers reach the model; listening acceptance is a separate requirement of the issue. This is not a claim that all emotion or segment-join timing problems are solved.
