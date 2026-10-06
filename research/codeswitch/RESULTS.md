# Hindi in an answer — FR-11.22 and EC-11.10, 2026-10-07

`probe.py` sent three kinds of audio to Groq `whisper-large-v3-turbo` under
three language settings. The rows are in `probe.json`.

- **Hindi:** eight clips of IndicTTS Hindi read speech (IIT Madras, CC BY 4.0).
- **English:** eight of day 6's IndicTTS English clips, Indian-accented.
- **Mixed:** four clips that join an English sentence and a Hindi one.

| Audio | `language=en` (M11 until today) | No language: Whisper detects | `language=hi` |
|---|---|---|---|
| Hindi (8) | **4 invented English**: "This is the end of the day.", "I have set your password to your chest…", "We are now watching the Jinn…", and one that read back the prompt ("I'm a project you built…"). 4 came back as Hindi in Latin letters. | **8 of 8 detected Hindi**, written as said in Devanagari, with English words kept ("password") | Same as detection |
| English (8) | Baseline | **8 of 8 detected English**, word for word the same as forced | All in Latin letters, but tagged Hindi |
| Mixed (4) | One lost its Hindi half entirely | Each part in its own language or script | Same as detection |

**What this decided:** M11 stops telling the recogniser to expect English
(`asr.py`, `M11_ASR_LANGUAGE=auto`).

**The reason** is that forcing English did not tolerate Hindi; it invented
English in its place. An answer would then be judged on words the student
never said, which is the penalty FR-11.22 forbids, and those invented words
could be cited as evidence. Detection kept every English answer exactly as
before.

**The safety net.** If detection names a language students here do not answer
in (for example, a short "Yes." heard as Welsh), the clip is transcribed again
as English.

**Downstream:**
- **M06** carries the detected language with the answer (`AsrNote.language`,
  `TurnView.language`).
- **M13** already scores content, never language. Its judge's rule 4 reads:
  "An answer in Hindi, Hinglish, or accented English is scored exactly like
  any other."
- **The notes** say so once: "You answered partly in Hindi. It was written down
  as you said it and scored on what you said — never on the language."

**Still owed:**
- **Real code-switched speech.** Hinglish within a sentence ("hash map ka
  lookup O(1) hota hai"), from consenting students. Read speech in two clean
  halves only approximates it.
- **The other Indian languages.** Only Hindi was measured here; the rest are in
  `SPOKEN_HERE` on the assumption that they behave the same, which has not
  been checked.
