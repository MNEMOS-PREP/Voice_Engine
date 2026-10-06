# How the voices say big-O — EC-11.11, 2026-10-07

`probe.py` had every voice in M11's cast (seven) read a form inside a carrier
sentence: "The time complexity here is ___, in the worst case." Each clip was
then transcribed cold, with no prompt. Round 1 used Groq Whisper directly.
Rounds 2 to 4 used M11's own recogniser: the product's ears on the product's
voice.

The cells count the voices, out of seven, whose clip came back as the form
itself or as its spoken words.

| Round | Form, as sent to the voice | O(1) | O(n) | O(n log n) | O(n²) | O(2ⁿ) |
|---|---|---|---|---|---|---|
| 1 `probe.json` | notation as written | 5 | 3 | 2 | 0 (`^2`), 4 (`²`) | 2 |
| 2 `said1.log` | "O of n", "O of one", … | 3 | 1 | 2 | 2 | 3 |
| 2 `said1.log` | "big O of n" | — | 3 | — | — | — |
| 3 `said_en.json` | "O of en", "O of en log en", … | — | 2 | 1 | 3 | 5 |
| 3 `said_capital_n.log` | "O of N", "O of N log N", … | — | 2 | 2 | 0 of 1 | — |
| 4 `said4.log` | **"order one", "order N", "order N log N", "order N squared", "order two to the N"** | **7** | **5 + 2 near** | **7** | **7** | **7** |

**What failed.** The voices lose whatever follows a bare "O". The usual
read-back was "The time complexity here is O, in the worst case." A synthesized
"O of n" is only about 0.3 s longer than "O" on its own, and once
("big O of n") it came out shorter. Lowercase single letters were swallowed
too: "on", "OR in", "Rn".

**What worked.** "order N". It is also how interviewers here say it aloud.
`notation.py` therefore rewrites big-O into that form before synthesis:

| Written | Said |
|---|---|
| `O(1)` | "order one" |
| `O(n)` | "order N" |
| `O(n log n)` | "order N log N" |
| `O(n^2)`, `O(n²)` | "order N squared" |
| `O(2^n)` | "order two to the N" |
| `O(V + E)` | "order V plus E" |

Single letters are written as capitals. Only the interviewer's audio changes;
the line on screen keeps its notation.

**How far to trust these counts.** Each count is one sample per voice, and the
voices sample with temperature 0.8, so two runs of the same sentence can
differ. The gap here (7 against 0–3) is far larger than that noise. M11 caches
the first sample of every sentence, so that sample is what students hear from
then on. Rerun `probe.py --said "…"` when the voice model changes.
