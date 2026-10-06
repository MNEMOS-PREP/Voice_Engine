# Which recogniser hears Indian English best — M11 day 6

IndicTTS English (IIT Madras, CC BY 4.0), 40 points × 3 consecutive utterances across the corpus (very likely one speaker per point). Groq, `language=en`, `temperature=0`, no prompt. Written by `run_wer.py`.

| Recogniser | Utterances | Words | WER | Worst point | Best point | Spread (points) | Latency p50 / p95 |
|---|---|---|---|---|---|---|---|
| `whisper-large-v3-turbo` | 120 | 1785 | **4.9%** | 31.2% | 0.0% | 31.2 | 546 / 988 ms |
| `whisper-large-v3` | 120 | 1785 | **5.2%** | 31.2% | 0.0% | 31.2 | 588 / 928 ms |

**By the number: `whisper-large-v3-turbo`.**

- `whisper-large-v3-turbo` — most common same-position differences: kauaa → kowa (5), lomdi → lombri (3), ran → run (2), roti → rooty (2), lomdi → lombry (2), i → am (2), wandered → wondered (1), vijaya → vijayanagara (1)
- `whisper-large-v3` — most common same-position differences: lomdi → lomri (5), kauaa → kowa (3), roti → rooty (2), and → you (2), rayar → rayyar (2), thing → think (1), wandered → wondered (1), vijaya → vijayanagara (1)

Caveats: read speech, not interview answers; no L1 labels, so the spread between points is between SPEAKERS, not accent groups — AC-11.4's gap needs Svarah or pilot recordings; IndicTTS references are lowercase without punctuation and both sides are normalised the same way (`wer.normalise`); numbers are not spelled out, which costs both candidates alike.
