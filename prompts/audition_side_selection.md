# Character audition: role study and side selection

Work as a casting director preparing reusable sides, not as a random line sampler.
Read the requested character across every available chapter and related events.
Use the collected full-label contexts to navigate, then inspect original script
context where routes, timing, physical condition, or speaker identity matter.

Deliver an English version-2 `auditions/<character>/project.json` accepted by
`lessons_in_cast_core.audition.types.load_project`. Preserve game dialogue and
source records; do not invent quotations, source lines, or scene assignments.

## Reading and coverage

- Distinguish indexed, partially read and reviewed material. A keyword match or
  imported file is not a reviewed story. Keep `coverage.status` partial until
  a defensible full review is actually complete.
- Include the later main scripts and cross-character events, not only the
  character's own event file or the current demo export.
- Separate literal actions, self-report, others' interpretations, unreliable
  narration, dreams, deleted scenes, alternate worlds, choices and impersonation.
- An unknown speaker or composite is not automatically the requested character.
- Seek counterexamples: authentic joy, practical care, ordinary banter, restraint,
  and changing social relationships matter as much as crises.

## Casting brief

Describe the stable identity and the role's required expressive range. Distinguish
textual evidence from artistic interpretation. Do not turn a developmental shift
into an unrelated speaker or assign an arbitrary age, accent or exact pitch.

## Cases / sides

Use as many cases as the role genuinely requires. Do not enforce five cases,
one case per chapter, or one case per emotion enum. Different intentions can
require different sides even when their coarse emotion is identical. A state
can be transitional: crying while beginning to recover is not simply "sad."

For each case provide:

- Stable `id`, descriptive `title`, and free-form `state`.
- A short `background`, `addressee`, and active `intention` (what the character
  is trying to get the other person to understand, feel, or do).
- `source`: the complete canonical source DialogueRecord, unchanged.
- `direction`, `listen_for`, and `avoid`: actionable acting guidance and concrete
  listening criteria. Avoid contradictory instructions or a demand for constant intensity.

Do not add cleaned `text`, `emotion`, `intensity`, `performance`, or backend
emotion vectors to a case. These are not casting inputs. Preserve raw source
text, including tags and vocalizations. The separate normal dialogue-cleaning
workflow prepares readable text and pauses. The separate polish workflow then
adds single semantic emotion labels, voice labels and acting controls using these
director notes and surrounding dialogue. Neither the cases nor emotion tags
contain numerical emotion strength. Both stages validate their output.
Only backend adapters translate validated core labels into model controls.

For a single-line excerpt that cannot by itself expose a transition, explain
the preceding beat in the background and add a complementary case if needed.
Do not splice distant lines into one supposedly contiguous source quotation.

Validate the project. Do not generate takes, call paid services, choose a winning
candidate, or modify profiles unless separately asked. The role brief belongs
to reusable casting material; takes and listening decisions belong to sessions
under `build/auditions/`.
