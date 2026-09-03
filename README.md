# Lessons in Cast

Lessons in Cast is a work-in-progress pipeline for adding generated voice audio
to Ren'Py games. It extracts dialogue, applies deterministic and AI-assisted
text annotations, generates speech with GPT-SoVITS, and prepares the resulting
audio for integration into a game release.

```text
Ren'Py scripts -> dialogue extraction -> stream processing -> annotation
              -> speech synthesis -> audio integration
```
