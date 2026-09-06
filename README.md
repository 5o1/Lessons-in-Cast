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
