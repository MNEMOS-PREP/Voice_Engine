# Listening test — which interviewer sounds like a person?

The same interviewer lines in each candidate voice, side by side, with a blind
mode (shuffled, names hidden) for a team or student panel. Started 2026-10-05
after the browser voice was judged "like an AI" — see the M11 TODO §0 entry of
that evening for the research behind it.

Open `listen.html` in **Microsoft Edge**: "Today" plays the voice students hear
now, live, through the browser's own speech.

## What is in it

| Candidate | Script | Notes |
|---|---|---|
| Today — Edge's Neerja voice | (live, in the page) | browser speech synthesis |
| Chatterbox Turbo, built-in voice | `make_chatterbox.py` | Resemble AI, MIT, offline; ≈ 4.5× slower than real time on an i7-1260P CPU |
| Chatterbox Turbo, cloned from DailyTalk | `make_chatterbox_clone.py` | the two speakers of DailyTalk (CC BY-SA 4.0), ~12 s of their own conversation each — **research only** |
| Orpheus on Groq | `make_samples.py` | needs the Groq org admin to accept the model's terms first |
| Gemini 3.8 Flash TTS | — | needs `GEMINI_API_KEY` in `keys.txt` |

Each line exists twice — as the interviewer writes it today, and rewritten for
the ear — so the test separates what the voice adds from what the words add.
`check_words.py` reads every clip back with Whisper and flags any that does
not say its line (`words.json`).

## Regenerating

The WAVs are not in git (`*.wav` is ignored). Chatterbox needs its own venv:

```bash
python -m venv tts-venv && tts-venv/Scripts/python -m pip install chatterbox-tts
tts-venv/Scripts/python make_chatterbox.py          # downloads ~3.8 GB once
tts-venv/Scripts/python make_chatterbox_clone.py    # needs reference/dailytalk_*.wav
python build_page.py
```

The DailyTalk reference clips come from the `DynamicSuperb/DialogueActClassification_DailyTalk`
mirror on Hugging Face (files `{turn}_{speaker}_d{dialogue}.wav`). Attribution:
Lee et al., "DailyTalk: Spoken Dialogue Dataset for Conversational
Text-to-Speech", ICASSP 2023, CC BY-SA 4.0.
