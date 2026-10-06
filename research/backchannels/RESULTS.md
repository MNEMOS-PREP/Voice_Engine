# Which "mm-hm" sounds like one? — FR-11.11, 2026-10-06

`probe.py` had every voice in M11's cast (seven: Chatterbox's own, DailyTalk 0,
five IndicTTS speakers) say each candidate backchannel. Each clip was timed and
read back by Groq `whisper-large-v3-turbo`. The rows are in `probe.json`.

| Candidate | Heard as itself, ≤ 1.1 s | Median length | What went wrong |
|---|---|---|---|
| **Okay.** | **7 / 7** | 720 ms | — |
| **Sure.** | **7 / 7** | 760 ms | — |
| **I see.** | 6 / 7 (7 by ear) | 960 ms | one voice transcribed as "IC", which is the same sound |
| Got it. | 6 / 7 | 800 ms | "Good deal." in IndicTTS 063175 |
| Mm-hm. | 3 / 7 | 1,520 ms | "Mmm. Mmm.", "Mm-mm" (a *no*), over 2 s in three voices |
| Mhm. | 3 / 7 | 920 ms | "Mm. Muh.", "this" |
| Hmm. | 3 / 7 | 760 ms | "1.", "Mmh.", "Mm-hmm." |
| Uh-huh. | 2 / 7 | 1,480 ms | doubled ("Uh-huh. Uh-huh."), "A-hok-da-h-u" |
| Mm-hmm. | 1 / 7 | 1,440 ms | "M-5", "Mm. Mm. Mm." |

**What this decided.** The synthetic voices say words well and non-words badly.
The sounds people make most while listening ("mm-hm", "uh-huh") come out
stuttered, doubled, too long, or as the opposite ("mm-mm"). A backchannel that
sounds like a glitch is worse than having none. M06's phrasebook therefore
uses only words (`BACKCHANNELS`, M06 `870f184`):

- friendly register: "Okay.", "I see.", "Sure."
- neutral: "Okay.", "I see."
- bar-raiser: "Okay." — and none at all in Final Boss (spec FR-11.11)

**Revisit when** the voice model changes. A better model, or Orpheus behind
day 8's flag, may say "mm-hm" properly. Rerun `probe.py` against it. The words
can move back to sounds only if the sounds pass this same check.
