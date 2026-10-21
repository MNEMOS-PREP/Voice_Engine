# What an interviewer says after an answer — 2026-10-21

The user, after a mock: "when my answer is correct it moves to the next
question without anything like hmm, good, well said — it should be a mix of all
possible words, and sometimes just the next question". `probe.py` had every
voice in M11's cast (eight: Chatterbox's own and seven IndicTTS speakers) say
each candidate. Each clip was timed and read back by Groq
`whisper-large-v3-turbo`. The rows are in `probe.json`.

M11 keeps each voice's first render of a sentence for good, so the render
probed here is the one students hear. A word one voice garbles stays garbled in
that voice.

| Candidate | Came back as itself | Median | What went wrong |
|---|---|---|---|
| **Okay.** | **8 / 8** | 840 ms | — |
| **Very good.** | **8 / 8** | 960 ms | — |
| **Nicely put.** | **8 / 8** | 1,240 ms | — |
| **That makes sense.** | **8 / 8** | 1,520 ms | — |
| **Got it.** | 7 / 8 | 880 ms | "Got you." once, which still reads as an acknowledgement |
| **Hmm, I see.** | 8 / 8 | 1,520 ms | — (three voices run 1.7–1.9 s) |
| **Hmm, okay.** | 6 / 8 | 1,440 ms | the "hmm" lost twice, leaving "Okay." |
| **Okay, thank you.** | 7 / 8 | 1,640 ms | the "okay" lost once, leaving "Thank you." |
| **Good, thank you.** | 8 / 8 | 1,640 ms | — (heard as two sentences) |
| **Nice, thank you.** | 8 / 8 | 1,600 ms | — |
| Sure. | 8 / 8 | 760 ms | clean, but answers a request, not an answer |
| Good. | 7 / 8 | 720 ms | **"bullet."** in IndicTTS 144039 |
| Nice. | 7 / 8 | 1,040 ms | "Nice. What, what, what do you…", 2.2 s, in 128877 |
| Well said. | 6 / 8 | 1,200 ms | **"Wang said"**, "When said" |
| Fair enough. | 7 / 8 | 1,040 ms | "Sad enough." |
| I see. | 7 / 8 | 1,000 ms | "I see. I, lause?", 2.1 s, in 002527 |
| Hmm. | 6 / 8 | 760 ms | "Mmm. Audi next.", 1.8 s |
| Right. | 5 / 8 | 760 ms | "That", "Alright!", "write." |
| Understood. | 5 / 8 | 1,080 ms | "on twist tooth.", "and disturbed.", "Underdood." |
| Alright. | 7 / 8 | 920 ms | "All eight" (Whisper writes the rest "All right") |

**What this decided.** M06's phrasebook (`ACKNOWLEDGEMENTS`, `CREDIT`) uses only
the bold rows. The words the user named come out as their clean neighbours:
"good" as "Very good." or "Good, thank you.", "well said" as "Nicely put.",
and "hmm" as "Hmm, okay." or "Hmm, I see.". A "hmm" on its own garbled in one
voice, but in front of a word it at worst disappears.

**Found on the way.** "I see." is also one of M06's backchannels (said softly
while the student talks). IndicTTS 002527's kept render of it has a garbled
tail. Deleting that one cached file lets M11 make it again.

**Revisit when** the voice model changes: rerun `probe.py`.
