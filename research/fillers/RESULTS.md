# Keeping "um" and "uh" — M11, 2026-10-23

`probe.py` sent clips to Groq `whisper-large-v3-turbo` under different
prompts. The rows are in `probe.json` (first run) and `confirm.json` (second
run).

**The audio.** DisfluencySpeech (AMAAI Lab, SUTD; Apache-2.0): conversational
speech whose annotated transcripts mark every filled pause (`{F uh, }`), so
each clip's true number of fillers is known. Each run used:

- 30 clips with fillers;
- 10 clips with none, as the control for invented fillers;
- 3 s of silence and 3 s of room noise.

**The prompts.** Each starts with the question, as M11 sends it.

| Prompt | Fillers kept, run 1 | Fillers kept, run 2 (new clips) | Invented on clean clips | Word errors, rest of the text |
|---|---|---|---|---|
| `today`: the question alone | **0 / 53** | — | 0 | 10.5% |
| `openai`: + "Umm, let me think like, hmm... Okay, here's what I'm, like, thinking." | 3 / 53 | — | 0 | 8.8% |
| `plain`: + "Um, so, uh, let me think. Uh, okay, um, here's what I did." | **35 / 53** | **30 / 44** | 0 | 6.5% · 4.7% |
| `short`: + "Um, so, uh, let me think. Uh, okay, um." | — | 23 / 44 | 0 | 5.0% |

**What this decided:** M11 ends its prompt on the `plain` line
(`asr.SPOKEN_STYLE`).

**Why:**

- **The question alone loses every filler.** M06's delivery notes count
  "um" and "uh", and they had nothing to count.
- **The plain line keeps two in three,** consistently across both sets of
  clips (35/53 and 30/44). It invented none on the 20 clean clips, and added
  one extra filler across 60 clips that had them.
- **It also improves the rest of the text.** Error on the non-filler words
  fell from 10.5% to 6.5%: written without its pauses, disfluent speech had
  been tidied into words nobody said.
- **OpenAI's own example line barely helps** (3/53). Its "umm", "hmm" and
  "like" are not "um" and "uh".
- **The shorter line drops the tail but keeps fewer fillers (52%),** so it
  was not chosen.

**Language detection (FR-11.22) is unchanged.** All 16 of `../codeswitch`'s
clips were detected exactly as before. English text came back word for word
on 7 of 8; the eighth, a sung passage, only differed in how two unusual words
were spelled ("gulmohars"/"gullmohars", "dalias"/"dhalias").

**Silence.** Every prompt makes Whisper write a sentence over silence or room
noise, the question alone included ("I'm going to go to the next slide.").
With `plain`, one such sentence ended "…what I did", the line's own words.
The defences are unchanged:

- the browser sends audio only after it has heard speech;
- M11 drops segments that are probably not speech (`shape`).

**Still owed:**

- **Real interview answers in Indian English,** from consenting students.
  This corpus is one American speaker re-performing Switchboard
  conversations.
- **"Er", "ah" and "hmm"** were not measured.
