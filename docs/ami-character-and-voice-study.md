# Ami: character development and voice direction

Status: **preliminary, source-grounded study; exhaustive reading is not complete**.
Source: the local `LessonsInLove0.60.0-0.60.0-pc-subscribestar` release.
Review date: September 8, 2026. Contains major story spoilers.

## Scope and evidence quality

The first lexical search found 895 candidate labels across 53 script files. These
are candidates, not 895 distinct Ami events and not a completeness guarantee.
They include passing mentions, combined speakers, optional branches, deleted
scenes, and exceptional narrative settings. Conversely, unnamed speech and
pronoun-only references can escape the search.

This pass covers selected material from the opening, chapters 2 and 3, chapter 4,
and `chap4part2`, plus personal and shared events. The coverage ledger records
27 selected-text passes, one additional low-relevance text pass, six speaker-only
passes, and ten partial label reads. All other indexed labels remain pending.
The reader extracts dialogue, narration, and selected control-flow statements;
it does not substitute for checking complete raw scripts, visual direction,
multiline strings, or playable routes.

Local research artifacts, intentionally under ignored `build/`:

- `build/research/ami/inventory.json`: lexical candidates and source ranges.
- `build/research/ami/coverage.json`: actual reading status, limitations, and source hashes.
- `build/research/ami/read_story.py`: source reader with original line numbers.
- `build/research/ami/record_review.py`: reproducible coverage ledger writer.

All source locations below are relative to the release's `game/` directory.
Line numbers refer to this local release, not an upstream edition. Evidence is
paraphrased; raw game dialogue and audio are not copied into this document.

Separate these evidence classes before drawing conclusions:

- Ami's ordinary on-screen actions and speech.
- Her retrospective accounts and self-descriptions, which can be incomplete or strategic.
- Other characters' assessments, which reveal their perspective rather than settle facts.
- Sensei's narration, especially during explicitly unreliable perception.
- Dreams, altered worlds, loops, apparent impersonation, and branch-dependent events.

Speaker `a` alone does not establish that a passage documents ordinary Ami.
For example, `amidate50p4` eventually has her describe Sensei as asleep during
the preceding journey (`AmiEvents.rpy:5097`). Its earlier apparent conversation
cannot simply become a list of her confirmed beliefs. Likewise, reports about
previous loops and the alternate-world Halloween sequence need separate tags.
Deleted scenes and alternate joke/censorship branches must not silently become
the main biographical timeline.

## Working character portrait

The most useful working interpretation is not "a cheerful girl who becomes
crazy." Ami repeatedly treats being indispensable to Sensei as security against
another loss. Genuine pleasure, attachment, practical care, rivalry, fear, and
attempts at control coexist. Development changes how she pursues security; it
does not erase every earlier trait.

| Dimension | Evidence | Interpretation and counterweight |
| --- | --- | --- |
| Care as a role and a source of worth | `AmiEvents.rpy:504`, `:1741`; `ch2script.rpy:4737`; `DormEvents.rpy:29465` | Cooking, cleaning, and managing daily life are more than a cute domestic habit. Being needed helps define her place. This does not make every act of care insincere. |
| Loss remains active, not resolved backstory | `AmiEvents.rpy:3961`, `:4606`, `:6966`; `chap4part2.rpy:1453` | Grief can abruptly interrupt ordinary conversation even late in the story. Her account of her mother also contains idealization and longing. |
| Real enjoyment and relationships beyond Sensei | `AmiEvents.rpy:4185`, `:4375`, `:4418`, `:5623` | Anime enthusiasm and reaching out to Molly and Rin are counterexamples to treating all cheerfulness as a calculated disguise. |
| Ability to notice and care for others | `AmiEvents.rpy:2871`, `:5864`; `chap4part2.rpy:1538` | She protects a resting friend's comfort, steadies Sensei when he is unwell, and provides practical care. A quiet, capable mode belongs in her range. |
| Fear of replacement can become exclusion and control | `AmiEvents.rpy:7549`; `chap4.rpy:6504`, `:6749` | A relationship can be treated as a finite resource that other people dilute. She may try to preserve dependency rather than welcome recovery or independence. |
| Vulnerability and harmful behavior can coexist | `AmiEvents.rpy:8519`, `:8886`, `:10522`, `:10977` | Fear, guilt, and a history of carrying responsibility help explain behavior without excusing coercion or harm. Avoid reducing these scenes to an entertaining villain stereotype. |
| Later composure is not necessarily recovery | `AmiEvents.rpy:9944`, `:10033`; `NikiEvents.rpy:6238` | She becomes more explicit about concealing feelings and more deliberate about questioning others. A restrained delivery can represent tactics, not emotional health. |

These are literary interpretations, not psychiatric diagnoses. Intelligence,
truthfulness, and emotional stability should not be inferred from Sensei's
insults or a single narrator description. Ami can reason precisely about
relationships while behaving irrationally when her security feels threatened.

## Provisional developmental map

The rows are narrative milestones, not chapter-wide emotion presets. Some are
temporary states, some are changes in relationship strategy, and backstory is
revealed retrospectively. Exact route prerequisites still require auditing.

| Milestone | Narrative basis | Voice-direction inference |
| --- | --- | --- |
| Retrospective foundation: loss and assuming responsibility | `amiinvite1`, `amidate50`, `amiinvite4`, and `amispring3` reveal shared hardship, her mother's importance, and early caregiving. | Explains later delivery; does not justify inventing a childhood voice or making current Ami sound like a mature maternal narrator. |
| Early domestic Ami / the cultivated "Mega Ami" role | Opening `script.rpy`, early room events, and `ch2script.rpy` `day271`. Familiar scolding, jokes, affection-seeking, and practical help already coexist with abrupt topic refusal. | High, light, quick everyday speech. Familiarity should sound effortless, not like every sentence is a cute performance. Allow a brief firm boundary without a new voice. |
| Growing insecurity and exposed dependence | The date chain, `aminew2`, `amidorm40`, `amispecial50`, and its main-story follow-ups. Friendship exclusion, grief, and uncertainty about her place become harder to contain. | Distinguish genuine ease from reassurance-seeking brightness. Questions can hang briefly for an answer; a joke may arrive too quickly to cover hurt. Quiet support remains possible. |
| Acute crisis and attempts to preserve a closed world | `chap4.rpy` `springend2` / `springend3`, then `AmiEvents.rpy` `amispring1` (Della). Care, denial, bargaining, panic, and guilt shift rapidly. | Follow each change of intention. Speech can accelerate or fragment; peaks may rise sharply. Do not turn the entire period into shouting or apply a permanent shriek timbre. |
| Withdrawal and tentative acceptance of being cared for | `amicamp1` / `amicamp2`, with the intervening `chap4hub.rpy` care loop. Shame, fear of abandonment, and tentative reassurance coexist with unresolved warning signs. | Reduced initiative and energy, hesitant starts, and fragile relief. Keep recognizable pitch and resonance; quietness is not necessarily whispering, adulthood, or full recovery. |
| More guarded, strategic expression | `halloweenami1`, `amispring2` / `amispring3`, `nikispring3` / `nikispring5`, and branch-dependent `amispring5`. Comfort, bargaining, concealment, and coercion can share a composed surface. | Controlled pacing, selective emphasis, and questions that hold their ground. Maintain the familiar light voice rather than switching to a generic low villain voice. Failed tactics can still expose raw fear. |
| Late coexistence rather than a completed transformation | `chap4part2.rpy` `dormwarssix4`: overt dependency-seeking exists alongside practical care and renewed pain about her mother. | Preserve access to warmth, ordinary humor, and grief. A single "late dark Ami" preset would misread the available material. |

The Old District incident has conflicting accounts from Ami and her friends
(`amispecial50` versus `amispecial50mainp1`). Maya's descriptions of previous
loops are reported testimony. Neither should be flattened into an unquestioned
chronological record. Alternate-world Halloween events likewise need their own
context rather than automatically constituting Ami's next developmental stage.

## Inferring a voice without inventing a canonical recording

There is textual support for a perceived high register: Tsuneyo calls out Ami's
high-pitched voice during a roast (`chap3.rpy:8880`). This is a character's comic
assessment, not an acoustic measurement. The script does not establish a precise
fundamental frequency, formant profile, accent, or a specific actor's voice.

The user's desired very high breakdown peaks are an artistic constraint. They
are compatible with some crisis scenes, but the reading does not establish a
literal whistle-register requirement.

### Stable identity: proposed audition target

- A recognizably high, light female voice, with enough body to avoid a thin,
  permanently squeaky result.
- Clear conversational English and relaxed articulation: intelligible without
  punching every consonant or stretching every emotionally colored word.
- Agile reactions and easy domestic banter, not obligatory sing-song endings.
- A usable soft-speaking range at the same identity; neither constant breathiness
  nor a forced low, mature, soothing register.
- Enough expressive headroom for a sudden bright appeal, a firm short refusal,
  restrained hurt, and genuine loss of composure.

All five points are **design hypotheses**, not facts read directly from the game.
Choose the identity by listening; the text alone cannot uniquely determine it.
Reject a design that only sounds convincing while excited or while whispering.

### Performance dimensions, independent of identity

| Mode | What should change | What should not be assumed |
| --- | --- | --- |
| Ordinary care and banter | Natural pace, small reactions, light familiar scolding. | Care does not imply slow maternal warmth. |
| Sincere enjoyment | Spontaneous variation and responsiveness to the other person. | All happiness is not a mask. |
| Brightness used to secure reassurance | Slightly more deliberate sweetness; attention to whether the other person answers. | This should not advertise a villainous intention on every line. |
| Grief or shame | Reduced projection, uneven initiation, meaningful silences where supported. | Quiet speech is not automatically whispering or a lower identity. |
| Panic and bargaining | Acceleration, repetitions, unstable breath groups, motivated pitch peaks. | No screaming unless the individual scene warrants it. |
| Guarded control | Deliberate phrasing and selective emphasis; calm delivery can remain light. | Later characterization does not require a deeper voice. |

Dreamlike distortion, apparitions, and unusual perceptual effects belong to the
specific line or scene's rendering context, not an irreversible alteration of
Ami's global voice identity.

## Consequences for the current opening demo

Even the opening needs more than "cheerful Ami":

1. Waking Sensei moves from calling for his attention to familiar impatience.
2. His confusion triggers practical concern and attempts to understand him.
3. The optional question about her parents meets an abrupt repeated refusal
   (`script.rpy:739`), not a playful pout.
4. Everyday guidance and familiar joking resume; she also mediates the encounter
   with Maya. These do not require carrying the later crisis's intensity backward.

Therefore, the previous generic light/soft/understated voice-design prompts are
not sufficient character briefs. They describe delivery preferences while
omitting what makes Ami recognizable. Conversely, packing every later spoiler
into an opening-voice prompt would encourage unwarranted dramatic emphasis.

The next audition should first compare neutral identity candidates using at
least five different ordinary lines. Once an identity is selected, test a small
contrast set: everyday banter, sincere delight, practical reassurance, a short
boundary-setting response, and restrained hurt. Crisis and guarded-control
delivery should be subsequent tests of that identity, not separate unrelated
voices. Whether a particular backend can preserve identity across these tests
must be verified experimentally.

## Remaining work before treating this as a full-story dossier

- Read the pending personal, dormitory, main-story, and cross-character labels;
  distinguish substantial evidence from passing mentions.
- Check unknown-speaker assignments, impersonation, composite speakers, and
  pronoun-only references that the lexical index cannot establish.
- Audit prerequisites, choices, jumps, retrospective passages, and alternate
  worlds before assigning precise scene-to-stage boundaries.
- Inspect raw text and visual direction for the scenes used as voice references;
  filtered dialogue alone can miss pauses, physical condition, or context.
- Keep deleted scenes and mutually exclusive branches separate, and record
  contradictions instead of silently reconciling them.
- Revisit the portrait against counterexamples and update its evidence ledger.

No profile, generation prompt, model setting, or audio asset was changed as part
of this study. The proposed stages are not implemented runtime presets.
