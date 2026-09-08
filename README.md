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
| Effects module | Design concrete audio effects and reusable effect chains. Voices associated with abstract-world entities, gods, and hallucinations should pass through purpose-built filters. | Design pending |
| Encoded-dialogue rendering | Design suitable rendering strategies for dialogue represented through ASCII encoding, Caesar ciphers, and related transformations instead of treating it as ordinary spoken text. | Design pending |
| Pause, delivery, and emotion refinement | Correct the many unnatural phrase boundaries found in the demo, reduce emotion emphasis where it is unwarranted, and improve the rendering of genuinely quiet speech. | In progress |
| Director (`Kantoku`) | Add a core director module. Before dialogue cleanup, the pipeline should load the matching configuration from the root-level `kantoku/` directory using the `name -> label -> scene` hierarchy. A configuration must be able to provide prompts describing scene background and character mental state for injection into the LLM cleanup pass. It may also define common rendering parameters for a label or scene. Merge configurations from general to specific with dictionary-update semantics: `name`, then `label`, then `scene`. Kantoku is the downstream override when a field also exists upstream—for example, it may replace a character's default profile from `characters.toml` within a particular section. This is intended to apply specialized acting direction across climax sequences. | Not started |
| Dialogue-cleanup pipeline redesign | Redesign the cleanup and annotation workflow to use language-model context more effectively while avoiding unnecessary token use. Define a detailed, efficient pipeline before running another large annotation pass. | Redesign planned |
| Web UI | Build an interface for assigning profiles to characters in particular scenes and for editing Kantoku prompts, background notes, and related direction. This is needed because anonymous speaker identifiers may represent different people, nominal speakers may be stand-ins, and characters such as Maya and Ami can change substantially across the story. | Not started |
| Incorrect `!` and `?` pause handling | [IndexTTS-only compatibility fix](docs/index_tts_punctuation.md): append explicit period cues after expressive punctuation, preserve pronunciation spans and emotion inputs, and record model frontend text for auditing. Other backends and shared audio concatenation remain unchanged. | Implemented; demo1 period-mode audition accepted; pending PR review ([#5](https://github.com/5o1/Lessons-in-Cast/issues/5)) |
| Abrupt high-volume cutoff | Fix the bug that causes some high-volume lines to end abruptly. | Open bug |
