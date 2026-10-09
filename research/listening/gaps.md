# The gaps in a spoken line — measured, and what removed them (2026-10-09)

The user, after a mock: *"I could feel gaps in speech, awkward pauses,
sometimes if the text is too long … use the smartest ideas to overcome
this"*, and *"no noticeable gaps, awkward pauses, or breaks between
speakers"*.

Laptop: i7-1260P (4 performance + 8 efficiency cores), 16 GB, Iris Xe.
Model: Chatterbox Turbo ONNX.

## Where the silence came from (`gap_bench.py`, fresh cache)

A line reaches the browser as pieces (sentences; the first cut at its first
clause; any sentence of 12+ words cut at its clauses), M11 makes them three
at a time, and the browser played each in its own `<audio>` when the one
before it ended.

| line | first sound | silence between pieces |
|---|---|---|
| "Okay. Tell me about the last project you worked on." | 3.1 s | 2.0 s stall after "Okay." |
| a two-clause question | 4.3 s | 2.9 s stall |
| a long follow-up (5 pieces) | **10.9 s** | 2.9 s stall mid-line |
| a hand-over (4 pieces, 2 voices) | 10.6 s | none |

Every join also carried 0.2–0.5 s of silence baked into the clips (each clip's
own tail and lead, plus three silence tokens the decoder adds), before the
next `<audio>` had even started. q4, or five rows, changed none of it: the
language model tops out near 27 speech tokens a second on this CPU, and
speech needs 25.

## What was tried and is not faster here

- **DirectML on the Iris Xe**, language model: 3.8 tokens/s (the CPU: 16–18);
  with the cache kept on the GPU, onnxruntime-directml 1.24 crashes (an empty
  tensor on the device; then in garbage collection).
- **DirectML, decoder**: 0.33–0.46× real time once compiled (the CPU:
  0.55–0.66×), but it recompiles for every new length (10–13 s) — usable only
  with fixed-length buckets, and the GPU shares the CPU's memory bandwidth.
  Not taken.

## What removed the gaps

1. **One track** (`@ai/core` v0.29.0, `player.ts`): every clip decoded as it
   arrives, trimmed to its sound, and scheduled on one Web Audio clock to the
   sample after the one before it — plus the pause a person leaves there
   (`track.ts`: ~0.1 s at a comma, ~0.3 s at a full stop, ~0.22 s when the
   speaker changes, by the speaker's tempo). A long line whose rest is still
   being made holds its first word up to 1.2 s rather than stalling
   mid-sentence. Live: every join inside a line 0.11–0.41 s, none over 0.6 s.
2. **Lines made before they are said** (M11 warm lines, M06 `/upcoming`, the
   room's `warm.ts`): while the student reads the plan and while they answer,
   the room has M11 make the next question (M05's choice and two alternatives,
   after the lead-in it will follow) and the panel's stock phrases (names in
   place). Made only while nothing is being said; set aside the moment a live
   line arrives; the likely next line (`next`) before the stock phrases
   (`warm`), the newest first.
3. **The reply made while the student talks** (M06 prefill, FR-11.6): at each
   pause, the line the interviewer would say if the answer stopped there is
   made as a `next` line. Said only if it is the line the real answer gets.
4. **An int8 language model** (`int8.md`): a sentence alone is made at 41.5
   tokens a second against fp32's 16.4 — faster than speech — so the lines no
   one could predict (a follow-up adapted to the answer) come in seconds.
