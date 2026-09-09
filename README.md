# Lessons in Cast

Lessons in Cast is a work-in-progress pipeline for adding generated voice audio
to visual novels. Game-engine and speech-generation backends are replaceable;
Ren'Py is the default game backend. It extracts dialogue, applies deterministic
and AI-assisted text annotations, drives replaceable speech backends, and prepares the resulting
audio for integration into a game release.

```text
galgame source -> backend extraction -> stream processing -> annotation
              -> speech synthesis -> audio integration
```

This is a source-workspace application. See [workspace setup](docs/setup.md)
and the [pipeline contract](docs/pipeline.md) for installation and operation.

## Development plan

| Title | Description | Status |
| --- | --- | --- |
| Character voice-reference selection | Early experiments followed a character casting list previously discussed by Selebus in the community, but the resulting voices differed substantially from the intended character impressions. Use voice-design models to create original character voices and reduce copyright risk. Every character should have at least five distinct reference utterances with natural delivery. Add references for other emotions and delivery styles as they become necessary; some characters, such as Ami, will require a substantial voice transition. | In progress |
| Effects module | [Configurable core effects](docs/effects.md): fade-in, fade-out, telephone degradation, monster pitch/bass, censor beep, and repeat/hold/dropout glitch. Compose dialogue-level chains and record processing parameters independently of TTS backends. | Initial implementation; audition review pending ([#1](https://github.com/5o1/Lessons-in-Cast/issues/1)) |
| Encoded-dialogue rendering | Design suitable rendering strategies for dialogue represented through ASCII encoding, Caesar ciphers, and related transformations instead of treating it as ordinary spoken text. | Design pending |
| Pause, delivery, and emotion refinement | Correct the many unnatural phrase boundaries found in the demo, reduce emotion emphasis where it is unwarranted, and improve the rendering of genuinely quiet speech. | In progress |
| Director (`Kantoku`) | Snapshot background, character state, and acting guidance from root-level `kantoku/` TOML files using the source name → label → scene hierarchy. Both annotation backends receive scoped guidance; production rendering applies profile/performance overrides downstream. See [configuration](kantoku/README.md). | Implemented; real-provider/listening evaluation pending |
| Dialogue-cleanup pipeline redesign | Cleaning and polish independently select Codex or a compatible API. API execution uses readable scripts, bounded evidence-backed story memory, structured output, local validation, and resumable commits. See [operation](docs/annotation-api.md). | Implemented; real-provider/listening evaluation pending |
| Web UI | Build an interface for assigning profiles to characters in particular scenes and for editing Kantoku prompts, background notes, and related direction. This is needed because anonymous speaker identifiers may represent different people, nominal speakers may be stand-ins, and characters such as Maya and Ami can change substantially across the story. | Not started |
| Incorrect `!` and `?` pause handling | [IndexTTS-only compatibility fix](docs/index_tts_punctuation.md): append explicit period cues after expressive punctuation, preserve pronunciation spans and emotion inputs, and record model frontend text for auditing. Other backends and shared audio concatenation remain unchanged. | Implemented; demo1 period-mode audition accepted; pending PR review ([#5](https://github.com/5o1/Lessons-in-Cast/issues/5)) |
| Abrupt high-volume cutoff | Fix the bug that causes some high-volume lines to end abruptly. | Open bug |
