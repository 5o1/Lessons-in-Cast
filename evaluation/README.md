# Annotation evaluation

Create a UTF-8 JSON Lines gold file following
schemas/evaluation-sample.schema.json, then run:

    lessons-in-cast evaluate --gold path/to/gold.jsonl

Gold samples are human decisions keyed by the stable dialogue IDs in
build/current/raw.jsonl. Keep evaluation data separate from model prompts and
responses so every model or prompt revision is measured against the same set.
