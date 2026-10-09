# Cutting a long sentence where a reader breathes (2026-10-10)

**Question.** A long sentence with no comma ("Recall a situation where you
were asked a question you didn't know the answer to during an interview.")
was one piece, made in one row of the language model. One row of three
makes ~19 speech tokens/s and speech needs 25, so a long piece made beside
others is late (a 14 s silence in the user's `demo_2`). Cut where a reader
breathes, its parts would be made side by side and joined on the room's one
track. Does a part made alone keep the sentence's tune?

**Method.** `breath_probe.py`: three long questions, said whole and cut in
two (with and without a comma closing the first part), in the cast's voices
through the running M11; pitch (pYIN) over the last voiced 250 ms of the
first part against the clip's median, in semitones; the same point in the
whole sentence (located by its share of the characters); read-back WER.
The run stopped after 8 of 12 rows (M11 reloaded under it); the rows are in
`breath/results.json`.

**Result: no.** The whole sentence at the cut point against the cut part's
end (bare / comma), semitones:

| voice, sentence | whole, at the cut | cut part's end |
|---|---|---|
| hr_nisha 0 | +2.4 | −6.8 / −5.0 |
| hr_nisha 1 | −4.3 | −3.5 / −4.3 |
| hr_nisha 2 | −5.7 | −6.1 / −8.1 |
| db_neha 0 | −0.3 | −1.3 / +3.4 |
| db_neha 1 | −2.2 | −4.6 / −3.1 |
| db_neha 2 | −0.1 | +3.4 / −2.7 |
| bar_raiser 1 | +0.8 | −5.7 / −2.1 |

In about half, the part ends 3–9 semitones lower than the sentence does at
that point — as low as a sentence's own end (−7 for hr_nisha) — so the line
would be heard as a string of sentences. A closing comma helps a little on
average (mean |difference| 2.8 st against 3.4), not enough. Every version was
read back right; a long whole sentence was the one misread most (bar_raiser 0:
WER 0.28 whole, 0.06 and 0 cut).

**So:** no cuts beyond the punctuation the text has. The gaps in `demo_2`
were mostly the CPU: clips made during it took 2–4× as long as the same
lengths before it (a face build shared the CPU; `make_faces.py` now waits
while an interview is on). For a long sentence, the next step is to keep it
whole and play it as it is made: decode its speech tokens in chunks while
the language model is still choosing the rest.
