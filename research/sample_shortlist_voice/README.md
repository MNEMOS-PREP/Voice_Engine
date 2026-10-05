# Shortlisted interviewer voices

The voices the team picked in the blind listening test (2026-10-06), one folder
per interviewer, each with the same three lines:

- `0_own_greeting.wav` — the interviewer's own opening line from M06's persona file, made by M11's live voice service (`POST /v1/voice/speak`)
- `a_greeting.wav` — "Hi! Thanks for making the time…"
- `b_question.wav` — "Okay, so. Say two keys land in the same bucket…"
- `c_follow-up.wav` — "[chuckle] Right, chaining, the classic…"

All made with Chatterbox Turbo (Resemble AI, MIT) on a laptop CPU.

| # | Interviewer | Voice | Accent | Status |
|---|---|---|---|---|
| 1 | Meera · Campus Recruiter | Indian voice 3 (230 Hz) | Indian | picked |
| 2 | Arjun · Bar Raiser | Indian voice 5 (111 Hz) | Indian | picked |
| 3 | Dr. Raghavan · Professor | Indian voice 6 (120 Hz) | Indian | picked |
| 4 | Priya · Senior Engineer | Chatterbox voice (236 Hz) | foreign | picked |
| 5 | Kabir · Founder | Conversational voice A (132 Hz) | foreign | picked |
| 6 | Sunita · HR Partner | Indian voice 1 (180 Hz) | Indian | **proposed** — fills a gap; swap freely |
| 7 | Vikram · Staff Engineer | Indian voice 4 (105 Hz) | Indian | **proposed** — fills a gap; swap freely |

The casting the platform actually uses is `Backend/backend_M11_Voice_Engine/voices/cast.json`.

## Credits

- Indian voices: **IndicTTS, SMT Lab, IIT Madras** — CC BY 4.0, English recorded by
  native speakers of Indian languages for speech synthesis.
- Conversational voice A: **DailyTalk** (Lee et al., ICASSP 2023) — CC BY-SA 4.0,
  academic use.
- Chatterbox voice: **Chatterbox, Resemble AI** — MIT.

These are AI voices: none is the person recorded, and none may be presented as a
real person. The WAV files are not in git (`*.wav` is ignored); regenerate them
from `research/listening/`.
