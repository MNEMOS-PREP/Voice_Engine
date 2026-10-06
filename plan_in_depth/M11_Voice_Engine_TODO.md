# M11 — TODO · Voice & Conversation Engine

> **Completion: 20%** — 3 of 22 functional requirements met (FR-11.8 barge-in, 11.13 repeat from cache, 11.21 a voice per persona), 3 partly (FR-11.1, 11.4, 11.7). **Days 1–3 and 7 of 14 (Revision 2) done, 2026-10-06:** the frame, the voice check, the latency ledger, barge-in measured from the student's first word, and the interviewers' own voices — Chatterbox Turbo on the server, cast per persona after a blind listening test, mostly Indian. M06's panel speaks in them, each panelist in their own voice. The spec has a Revision 2 (§0 of the spec): browser-first and free. The requirement count is the spec's own, so this is a measure of scope ahead rather than of progress behind.
>
> _Method: `(met + ½ × partial) ÷ total`, counted from the spec, 2026-08-28. One measure applied the same way to all nineteen modules so they compare; it counts requirements, not screens or gates._

Task list for taking **M11 — Voice & Conversation Engine** to 100% of [M11_Voice_Engine.md](M11_Voice_Engine.md).

> **This is the branch that holds the plan.** The `todo` branch carries the
> spec and this list and nothing else, so the module's own history stays
> about its code. Sync it here when something lands.

> **Read this first when starting a session on M11.** It is the running state of
> the module: what is done, what is next, and what is deliberately deferred.
> Update it as things land — a stale list is worse than no list, because the
> next session trusts it.

- **Repo:** `Voice_Engine`

Legend: ✅ done · 🟡 partly done · ⬜ not started

---

### 2026-10-06 — Day 3: barge-in, measured from the student's first word

- ✅ **The mic, listening** (`@ai/core` v0.18.0 `734f2f8`, v0.18.1 `d63a4c8`):
  `useListening` opens the microphone with echo cancellation, noise
  suppression and gain control, cuts it into 20 ms frames on the audio thread
  (an AudioWorklet from a Blob; an analyser where there is none), and says
  when speech starts — dated from its first loud frame — and ends. Nothing is
  recorded or sent: the frames are levels, read and dropped.
- ✅ **The rule is the spec's own** (§6.5, `vad.ts`, pure, 8 tests): 12 dB over
  the noise floor, sustained 250 ms (EC-11.14), dips between syllables
  forgiven. The floor follows the room down fast and up slow, never on speech,
  so a talker does not raise the bar against themselves; the bar rises 6 dB
  while the interviewer speaks (Trap 5 — echo cancellation leaves some); loud
  but FLAT energy (a fan switching on) is learned as the room, because
  syllables rise and fall and noise does not.
- **Decided: energy, not Silero, for the stop.** §6.5's barge-in rule is
  energy; it needs no model download and works on the demo laptop with no
  network. Silero (and Smart Turn) stay for endpointing — day 5 — where
  telling a pause from an end is the hard part.
- ✅ **`bargeIn(startedAt, { contest })`** stops every line still to be heard —
  the sentence playing, those queued, those still being asked of M11 (Trap 3:
  a stop that only silenced the speaker resumes mid-sentence) — and records
  `speech_started_at`. In our design a line lands whole before it is spoken,
  so there is no model stream to cancel; with v0.17.1's ordered requests, at
  most one sentence is being made, and nothing after it is asked for.
- ✅ **Final Boss contests, once a round** (§6.5; spec open decision 2 —
  **decided: on**, for the user's "test you, stress you"): the interviewer
  finishes up to 1.5 s before yielding. The line says `contested`, and the
  ledger lists it as its own stage, against no budget — the first live one
  read 1,763 ms against `barge_in`'s 600 before that.
- ✅ **The ledger** (Voice_Engine `0257db8`): `speech_started_at`, `contested`;
  stages `barge_in` (first word → silent, 600 ms = 250 + 350) and `contested`.
  45 tests.
- ✅ **M06's room: "Talk freely"** (M06 `cc4619c`): the mic open while the
  interviewer speaks; starting to talk stops them and starts dictation into
  the box. Off unless the student turns it on (remembered); a level meter;
  a blocked mic says how to allow it.
- **Measured live** (headless Edge, a fake microphone — room tone, then a
  voice at 6 s — over a panel's opening, M11's voices): Mock — first word to
  silence **261 ms** (speech decided at 260 ms, stopped in 1 ms; 56 of 221
  characters heard). Final Boss — the contest held 1.5 s, then stopped in 1 ms.
- **Next: day 4**, server ASR with word timestamps — the student's answer as
  audio, so the end of speech, not the send button, starts the clock.

### 2026-10-06 — The panel speaks, each in their own voice

- ✅ **M06's panel** (FR-6.3; M06 `d8a86ec`, `18c8c66`, `6e51c0a`): seated from
  the personas' data, introduced at the start, handing over in two voices,
  an expert's follow-up and the take-back, someone sitting in on a panel of
  one. Every line records who said it, part by part.
- ✅ **Each part in its speaker's voice** (`@ai/core` v0.17.0 `cacf1bb`):
  `speak([{ text, personaId, voiceId, id }, …])` says every sentence in its own
  speaker's voice — M11's cast voice, or the browser voice their `voice_id`
  picks; the ledger keeps the line as one line; `speakingPart` lights the
  right face. Heard live: Priya (`chatterbox-default`), Arjun
  (`indictts-022743`), Vikram (`indictts-063175`) in one opening.
- ✅ **Fixed: "Dr. Raghavan" was split after "Dr."** — a voice said "Dr." alone
  and paused, and M11 made two clips. A title's full stop no longer ends a
  sentence, and is said "Doctor".
- ✅ **Fixed: a line's first sentence waited behind its last** (v0.17.1
  `5e2ac60`). Every sentence was asked of M11 at once; M11 makes one at a
  time and which request won its lock was a race — a panel's opening waited
  five seconds while "Expect a follow-up or two." was made first. Sentences
  are now asked in speaking order, each when the one before is made; the
  next is made while the first plays. Throughput unchanged.

### 2026-10-06 — Day 7 pulled forward: the interviewers' own voices

- ✅ **Chatterbox Turbo on the server, via ONNX** (Voice_Engine `2aed9bb`):
  `tts.py` runs ResembleAI's ONNX export with no PyTorch, sampling as the
  PyTorch model does (temperature 0.8, top-p 0.95) — the model card's greedy
  loop spoke slower. `GET /v1/voice/engine` (off / loading / ready / failed),
  `GET /v1/voice/cast`, `POST /v1/voice/speak` (one sentence → 24 kHz WAV in
  the cast voice; signed-in callers; 503 until ready, so the browser voice
  speaks meanwhile). Every sentence is cached in memory and on disk: said
  once, instant after — which is what makes "repeat" (FR-11.13) instant.
  Synthesis is one at a time; two at once on a CPU only make both late. The
  model loads in the background at boot (~22 s).
- ✅ **The cast** (`voices/cast.json`, the user's picks after the blind
  test): Meera → IndicTTS 123823, Sunita → 017689, Arjun → 022743,
  Dr. Raghavan → 103607, Vikram → 063175 (all IndicTTS, IIT Madras, CC BY
  4.0, recorded for speech synthesis), Priya → Chatterbox's own voice, Kabir →
  DailyTalk speaker 0 (CC BY-SA, academic use). Seven personas, seven voices
  (FR-11.21). `ATTRIBUTION.md` credits each; the voice check shows the credits
  and says the voices are AI (India's IT Rules 2026 label synthetic audio).
- ✅ **The voice check speaks in them** (Voice_Engine `90063c9`): each
  interviewer in the voice students will hear, with whether it is ready.
- **Measured on this laptop** (i7-1260P, fp32): ready in 22 s; a line ~2.1×
  real time (Arjun's greeting 4.8 s); a cached line 0 ms. **The user's call:
  speed does not matter now — better machines later.** Live lines need a GPU
  box or the speculative pre-rendering idea in §0; neither is done.
- **Decided: Chatterbox replaces Kokoro / HeadTTS as tier 1** — the blind
  listening test chose it for sounding human, which is the user's measure
  ("not about accent — whether it sounds human").

### 2026-10-05 — Day 2: the latency ledger, and the first honest numbers

- ✅ **The browser records every spoken line** (Platform_Core `6791beb`, tag
  **v0.15.0**): landed, first audio, ended, or stop asked / stopped and why
  (mic, send, pause, end, repeat, off, leave; `barge_in` reserved for day 3),
  and how much was heard — through the word covering that point (§6.5). Rooms
  mark `answer_sent` and `first_token`. 7 tests (`npm test`).
- ✅ **M11 keeps them** (Voice_Engine `1f8ffe1`): `m11_line_timing`, marks not
  durations; `ledger.py` derives §11's stages on read and holds the targets;
  `POST/GET /v1/voice/{session_id}/timings` (idempotent on the browser's line
  id; the student who posts an interview's first line owns it; Platform_Core's
  stranger check pointed at `session_id`); `GET /v1/voice/timings/summary`
  staff-only, shown to staff on `/voice`. 23 tests; upstream probes stubbed
  so no test opens a socket.
- ✅ **M06 wired** (M06 `404647e`): the room passes its interview id, says why
  it stops the voice, marks the answer and the first token.
- **First numbers, live** (headless Edge, Neerja online voice, real model,
  6 lines in 4 interviews): answer sent → first audio p50 **1.11 s**, p95
  **1.41 s** (AC-11.1's 1.2 s — over); first token p50 718 ms / p95 957 ms;
  line on screen → first audio ~0.3 s, but **2–3 s for a page's first line**
  (the online voice's cold start); stop asked → stopped **6–9 ms**.
- **A false alarm, checked:** after End mid-line the browser was still
  "speaking" — the session's closing line ("That's time…"), said on purpose.
  The stop itself took 10 ms.
- **Next: day 3**, browser VAD barge-in — but see §0's entry of this evening:
  the voice's realism is now the open question, and its answer may reorder
  the days after it.

### 2026-10-05 — Day 1: the frame, and the voice client becomes M11's

- ✅ **The voice client moved to core** (Platform_Core `da448d5`, tag
  **v0.14.0**): `useInterviewerVoice` and `pickVoice` / `speakable` /
  `splitSentences` / `parseVoiceId` / `rateFor` / `kindOf`, with their 11
  tests (`npm test` in Platform_Core). M11's code, kept in core because M06's
  room and M11's voice check both use it and M14 will — §6's "graduate when a
  second module needs it", which day 1 triggered. M06 imports it from there
  (M06 `b3b401a`, core bumped in both package files and the lockfile).
- ✅ **The repo's frame** (Voice_Engine `77511e4`, `main`): `module.json`
  (M06 optional, with a sentence), ports 8111 / 5211 (8211 reserved for the
  WebSocket), the launcher (`start_voice.bat`, `start.bat`, `scripts/`), the
  identity guard on the router before any route, Platform_Core's stranger
  check from the first commit, and a gate that reads Platform_Shell's live
  proxy table to hold `/v1/voice` to M11. 6 tests, ruff clean, clean `tsc`.
- ✅ **The voice check, `/voice`**: every M06 interviewer, read from M06's
  persona files (`/v1/interviews/personas` now carries `voice_id` and the
  opening line — M06 `b3b401a`), each with the browser voice chosen for it and
  a Play button; the interview voice's on/off switch; "Arjun, Vikram,
  Dr. Raghavan and Kabir share Prabhat's voice; Meera, Sunita and Priya share
  Neerja's" — FR-11.21 measured in the browser, not assumed; when M06 is down,
  one sample voice under M06's own sentence.
- ✅ **Mounted in the shell** (Platform_Shell `f64d03e`): `/v1/voice` → :8111,
  source aliased, Tailwind scans it, reached from Settings → Voice and Ctrl K
  "Hear your interviewers". `start.bat` starts M11 and the HOME card checks it.
- **Checked live** in headless Edge through the shell: 326 voices; each
  interviewer gets Neerja or Prabhat (natural) by kind, at its manner's pace
  (Meera 0.97); Play speaks the greeting and the button turns to Stop at once
  (an online voice takes ~1 s to start); the degraded path renders. The M06
  room, now on core's hook, says its opening whole and the follow-up after an
  answer — the same speak/cancel trace as before the move.
- **Found on the way, fixed first** (M06 `ddd6fa5`): StrictMode's dev-only
  remount ran the room's unmount `cancel()`, which silenced every first
  question. The cancel now waits a tick and runs only if the room is gone.
- **Next: day 2**, the latency ledger.

---

### 2026-10-05 — Revision 2: browser-first and free; M06 speaks

- ✅ **Research (2026-10-04):** a sweep of ~480 GitHub repositories — faces,
  TTS, ASR, turn-taking, voice-agent frameworks, AI interviewers — plus README
  and licence checks on the candidates. The verdicts are §0 below; the
  decisions are the spec's new §0 (Revision 2) and §15.6.
- ✅ **M06 ships the first slice** (`voice-core.ts`, `voice.ts`, `ui/Face.tsx`):
  each line of record read aloud in the persona's `voice_id`; the face's mouth
  moves on each word; the voice stops when the mic opens, the answer is sent or
  the session pauses; one button turns it off. Verified in a headless Edge:
  Meera (`en-IN-female-warm`) → "Microsoft Neerja Online (Natural) - English
  (India)" at 0.97; first audio ~1.1 s after the line lands (the online voice's
  fetch); word boundaries reported. The persona card now carries `voice_id`,
  validated at load.
- ⬜ Everything below is still M11's: streaming the first clause, a VAD-driven
  barge-in, server ASR with word timestamps, Kokoro for browsers without a
  neural voice, audio-driven lip-sync, and the latency ledger.
- **Hardware note:** the development laptop's Intel Arc A370M (4 GB) has no
  driver installed (Windows problem code 28). Once installed it runs Intel's
  OpenVINO notebooks for Kokoro, Whisper, Wav2Lip, Parler-TTS and Qwen3-TTS/ASR —
  useful for the device matrix (day 14). No CUDA either way.

---

## 0. Ideas and scouting

Things worth building that did not come from the spec — usually from reading
somebody else's implementation. **New ideas go at the top of this section.**

The rule we keep arriving at: borrow a **technique**, not a **component**. The
platform's contracts — character offsets, per-fact provenance, permanent
evidence — are more demanding than general-purpose tools assume, so integration
usually costs more than reimplementing the one idea we actually wanted.

**2026-10-06 — the user's verdict, and a mostly-Indian roster.** After the
blind listening test: Chatterbox's built-in voice and the DailyTalk clones
were "pretty close — use both"; the roster should mix Indian and foreign
accents, mostly Indian. The engine is therefore **Chatterbox Turbo (MIT)**,
with cloned voices; persona `voice_id`s already carry the accent (`en-IN-…`,
and `en-US-…` / `en-GB-…` for the foreign few).

- **Indian voices:** IndicTTS (SMT Lab, IIT Madras; MeitY consortium) —
  English recorded by native speakers of Indian languages *for speech
  synthesis*, CC BY 4.0 (credit "IndicTTS, SMT Lab, IIT Madras"), confirmed on
  IndiaAI's AIKosh. Read via `SPRINGLab/IndicTTS-English` (151,640 utterances,
  no speaker labels): 29 samples at even offsets → **21 distinct voices** by
  Chatterbox's own speaker encoder (cosine > 0.86 = same voice) → six cast by
  pitch band and mutual difference (`pick_voices.py`), 18 clips, all but one
  read back right by Whisper (one garbled the word under a `[chuckle]`).
  Trade-off: IndicTTS is READ speech, so its clones lean narration;
  conversational Indian references would come from Svarah (AI4Bharat,
  CC BY 4.0, spontaneous speech, 117 speakers — gated on Hugging Face, the
  user's account must accept) or the team's own recorded voices.
- **Speed, measured (i7-1260P CPU):** PyTorch ≈ 7–9 speech tokens/s (real
  time needs 25) → 4.5× too slow. ResembleAI's ONNX export: **q4 27.2 tok/s**
  (language model 0.9× real time, one-step decoder +0.47× → 1.4× overall),
  fp32 17.6 tok/s (1.9×), q8 2.0 tok/s (pathological here). All read back
  right; greedy decoding (the model card's) speaks slower than PyTorch's
  sampling. **Not live on a laptop CPU** — an 8 s line needs ~3 s of buffer.
  Live lines need a GPU server (one cohort-wide box); fixed lines pre-render
  on CPU.
- **Idea — speculative synthesis:** M05's next bank question is one of a few
  candidates known before the student finishes answering; rendering those
  while the student talks (60–120 s of slack) would make most questions
  instant even on CPU. Probes adapted to the answer cannot be pre-rendered.

**2026-10-05 (evening) — "it sounds like an AI": what makes a voice human.**
The user's verdict on the browser voice, and the question it opened: not the
accent — whether it sounds like a person. Researched the same evening; the
listening test is in `research/listening/` (Voice_Engine).

- **What listeners hear as human** (the research): turns follow each other
  after ~200 ms on average across 10 languages (Stivers et al., PNAS 2009);
  natural talk carries ~6 disfluencies per 100 words, and "uh" / "um" are
  signals of a short / long delay, not noise (Clark & Fox Tree 2002); filled
  pauses raise perceived authenticity and audible breaths beat silent pauses
  for naturalness and recall (Székely et al. 2019, 2020); listeners say
  "mm-hm" on a low-pitch cue, ~700 ms after it (Ward & Tsukahara 2000).
- **The deciding result — Sesame's CSM:** blind raters could not tell its
  single lines from real recordings (≈ 50/50), but with 90 s of conversation
  around them they consistently picked the human. The gap left is
  conversational behaviour — timing, pauses, interruptions, emphasis — not
  timbre. So: voice AND behaviour, or the uncanny valley.
- **Why ours sounds like an AI**, cause by cause: a newsreader-style engine;
  our own sentence-by-sentence utterances (prosody resets, a gap per
  sentence); lines written for the eye, not the ear; 1.1–1.4 s answer →
  voice and a 2–3 s cold start on a page's first line (day 2's ledger); no
  backchannels; no breaths, "hmm", laughter.
- **Engines, ranked by blind "more natural" votes** (Artificial Analysis
  Speech Arena, Sep 2026): ElevenLabs v4 1321 · Qwen-Audio 3.1 1292 ·
  Cartesia Sonic 3.6 1278 · **Gemini 3.8 Flash TTS 1275** — free tier per
  third-party guides, ≈ $0.81 / audio hour paid; a `style` field and inline
  `<breath>` `<chuckle>` `<sigh>` `<short pause>` `<throat-clearing>`; Voice
  Design (a voice from a description) and Voice Replication (from reference
  AND consent audio). Groq Orpheus is on our key but needs the org admin to
  accept its terms; $22 / M chars.
- **Open weights:** best ranked are non-commercial (Breeze TTS 2, Fish S2,
  Voxtral — research / NC licences). **Chatterbox Turbo (MIT, 350M)** clones
  from ~10 s and performs `[laugh]` `[chuckle]` `[cough]`, watermarked —
  measured on this laptop (i7-1260P, CPU): **≈ 4.5× slower than real time**
  (a 7 s line in ~30 s). Too slow to voice live lines here; fine for
  pre-rendering fixed lines once.
- **Cloning a voice from an open dataset** (the user's question): technically
  the same trick. Licences differ — LibriTTS-R / Hi-Fi TTS CC BY 4.0 (but
  audiobook narration, and a clone copies the style of its reference),
  DailyTalk CC BY-SA 4.0 (conversational, recorded for conversational TTS),
  Expresso CC BY-NC 4.0 (improvised dialogue, 26 styles). A dataset licence
  is not the speaker's consent to become a product voice (Hugging Face,
  "Voice cloning with consent"); a celebrity or character voice is out —
  Arijit Singh v. Codible Ventures (Bombay HC, July 2024) enjoined AI voice
  cloning without consent; India's IT Rules (in force 20 Feb 2026) require
  synthetic audio that passes for real to be labelled.
- **Open decisions (the user's):** a Gemini key for the test; accepting
  Orpheus's terms; real human voices — who records, with consent — which
  would revise FR-11.21's "no cloning of real people" to "only with written
  and recorded consent, never a public figure, revocable, labelled as AI".

**2026-10-05 — the free field, by component.** Adopt = in the Revision 2
build; evaluate = measured against the alternatives before choosing; avoid =
licence or hardware rules it out.

| Component | What it is | Licence | Runs on | Verdict |
|---|---|---|---|---|
| Browser speech synthesis | Edge: neural en-IN voices (Neerja, Prabhat) + Indian languages; Windows Heera/Ravi; macOS Veena/Rishi | browser API | browser | **Adopted** (M06, 2026-10-05) |
| Kokoro-82M via `kokoro-js` / HeadTTS | TTS with word timestamps and visemes; RTF 0.27 on WebGPU, 1.45 on WASM | Apache-2.0 / MIT | browser | Adopt as tier 1 — American English only, 90–330 MB download, so opt-in |
| Pocket TTS (Kyutai) | 100M-param TTS, ~200 ms to first audio, ~6× real time on 2 CPU cores | MIT code; voices licensed one by one | CPU server | Evaluate against Kokoro |
| KittenTTS | tiny CPU TTS (15–80M ONNX) | Apache-2.0 code; KittenTTS 2 weights under a community licence | CPU | Watch the licence |
| Piper | fast local TTS | now `piper1-gpl`, GPL-3.0 | CPU | Replaced by Kokoro |
| Indic Parler-TTS (AI4Bharat) | Indian-language TTS, 880M | Apache-2.0 | Arc (OpenVINO) or GPU | Evaluate for Indian-English voices |
| Veena (Maya Research) | Hindi, Hinglish and English TTS | Apache-2.0 | GPU | Server-only option |
| Groq Orpheus | managed streaming TTS, American voices | paid, $22 per 1M chars | API | Tier 2, behind a flag |
| Silero VAD + `ricky0123/vad` | voice activity detection in the browser | MIT / ISC | browser | Adopt |
| Smart Turn v3.2 (Pipecat) | semantic end-of-turn, 8 MB, ~10–65 ms CPU, 23 languages | BSD-2 (code and weights) | CPU | Adopt — replaces training our own |
| TEN VAD | VAD | Apache-2.0 + Agora non-compete | — | Avoid |
| Groq `whisper-large-v3-turbo` | ASR; free tier 2,000 requests/day | free tier, then $0.04/hour | API | Adopt as primary |
| `faster-whisper`, `whisper.cpp`, WhisperX | local ASR; word alignment | MIT, MIT, BSD-2 | CPU (GPU for large-v3 live) | Fallback; WhisperX for M12 |
| Moonshine | low-latency streaming ASR | MIT (streaming and English models) | CPU | Evaluate |
| Vosk `en-in` | offline Indian-English ASR, 36 MB / 1 GB | Apache-2.0 | CPU | Evaluate — WER 36–49 on NPTEL |
| Oriserve Whisper-Hindi2Hinglish-Apex | Whisper fine-tuned for Indian-accented English | open | CPU/GPU | Evaluate on Svarah |
| Pipecat / LiveKit Agents | voice-agent orchestration, interruptions | BSD-2 / Apache-2.0 | server | Borrow techniques; LiveKit's SFU for M14 |
| DeepInterview | an open AI interviewer (LiveKit + Kokoro + Whisper, fully local option) | Apache-2.0 | — | Reference; its crossfaded video-loop avatar |
| LAM + gsplat renderer + `wav2arkit` | realistic 3D head from one photo, lip-synced in the browser | Apache-2.0 / MIT / Apache-2.0 | browser | Face option B (spec §15.6) |
| TalkingHead + HeadAudio | stylised 3D head, lip-sync from audio | MIT | browser | Face option C |
| MuseTalk, LiveTalking, Ditto, LatentSync | photoreal real-time lip-sync | various | NVIDIA GPU | Out on our hardware |
| Duix | avatar toolkit | custom licence | — | Avoid |
| Wav2Lip | lip-sync (an OpenVINO notebook exists) | research only | Arc (OpenVINO) | Avoid for the product |

---

## 1. Where the module stands

| | |
|---|---|
| Status | **Days 1–3 and 7 of 14 (Revision 2).** The frame, the voice check (`/voice`), the latency ledger, barge-in, and the interviewers' own voices (Chatterbox Turbo on the server, cast per persona). The voice client is M11's code in `@ai/core` (v0.18.1). |
| Spec | Written, and the source of every row below. |
| Scope | 22 functional requirements (18 of them P0), 9 acceptance metrics (4 release-blocking), 15 edge cases. |

### 1b. What the voice client already does (M11's, in `@ai/core` since v0.14.0)

| FR | What the browser voice does since 2026-10-05 (built in M06, M11's since day 1) | |
|---|---|---|
| FR-11.3 | Browser recognition in en-IN: final phrases into the answer box; no word timestamps — still M06's `speech.ts`, not counted here | 🟡 interim (M06) |
| FR-11.7 | The line read aloud after it lands, a sentence at a time — not a streamed first clause | 🟡 interim |
| FR-11.8 | The voice stops when the mic button is pressed — no VAD, not measured | 🟡 interim |
| FR-11.13 | "Repeat the question" says it again, interrupting | 🟡 interim |
| FR-11.18 | The room is text-first: every spoken line is on screen — M06's room, not counted here | ✅ in M06 |
| FR-11.21 | One voice per persona from its `voice_id`, paced by its manner; Edge has two neural en-IN voices, so personas of a kind share one | 🟡 interim |

Everything else below is ⬜. That is the honest state and
it is worth writing down rather than leaving three sections saying
_To fill in._ — the point of this list is that the next session can start from
it instead of re-reading a six-hundred-line spec.

---

## 2. Functional requirements

Spec §4, verbatim. This is the authoritative list.

| FR | | Priority |
|---|---|---|
| FR-11.1 | 🟡 WebRTC audio capture with echo cancellation and noise suppression — Revision 2: `getUserMedia` with echo cancellation, noise suppression and gain control (`useListening`, day 3); no utterance audio captured yet (day 4) | P0 |
| FR-11.2 | ⬜ Real mic check with a live transcription round-trip | P0 |
| FR-11.3 | ⬜ Streaming ASR with word-level timestamps | P0 |
| FR-11.4 | 🟡 VAD-based endpointing with a per-speaker adaptive threshold — the detector (§6.5's rule, a moving floor, `vad.ts`) runs and drives barge-in; ending a turn by it is day 5 | P0 |
| FR-11.5 | ⬜ Semantic endpointing to avoid cutting incomplete utterances | P0 |
| FR-11.6 | ⬜ Speculative LLM prefill on stabilised partial transcripts | P1 |
| FR-11.7 | 🟡 Streaming TTS with clause-level first chunk — M11's voice a sentence at a time, asked in speaking order so the first plays while the next is made; not yet cut at the first clause | P0 |
| FR-11.8 | ✅ Barge-in: full stop of LLM + TTS + playback within 350 ms — the detector stops playback, the queue and the requests; 261 ms first word → silent, 1 ms after the decision (day 3). Lines land whole, so no model stream is running to cancel | P0 |
| FR-11.9 | ⬜ Truncate the interviewer turn at `heard_up_to_ms` on barge-in | P0 |
| FR-11.10 | ⬜ Calibrated silence per persona/mode with no UI change | P0 |
| FR-11.11 | ⬜ Backchannels on a separate bus, disabled in Final Boss | P1 |
| FR-11.12 | ⬜ Note-taking pauses | P1 |
| FR-11.13 | ✅ Repeat-last-utterance from cache — M11 caches every sentence it makes (memory and disk), so a repeat is instant; said by whoever asked it | P0 |
| FR-11.14 | ⬜ Mid-turn modality switch preserving the partial transcript | P0 |
| FR-11.15 | ⬜ Low-confidence spans marked and excluded from evidence citation | P0 |
| FR-11.16 | ⬜ Natural clarification behaviour on low ASR confidence | P1 |
| FR-11.17 | ⬜ Bandwidth degradation ladder down to push-to-talk | P0 |
| FR-11.18 | ⬜ Live captions always on | P0 |
| FR-11.19 | ⬜ Per-turn audio stored, aligned to the transcript clock | P0 |
| FR-11.20 | ⬜ p95 end-of-speech → first audio byte < 1.2 s | P0 |
| FR-11.21 | ✅ Distinct voice per persona; no cloning of real people — seven personas, seven cast voices from speakers recorded for speech synthesis under CC BY (IndicTTS) / CC BY-SA (DailyTalk), each credited; no celebrity or character voice; labelled AI | P0 |
| FR-11.22 | ⬜ Code-switch tolerance without penalty | P0 |

---

## 3. Acceptance gates

Spec §13. A **[GATE]** is release-blocking; the rest are tracked.

| AC | | Target |
|---|---|---|
| AC-11.1 **[GATE]** | ⬜ p95 end-of-speech → first audio — measured from "answer sent": 1.41 s (n=2), over | ≤ 1.2 s |
| AC-11.2 **[GATE]** | ⬜ Barge-in stop — a stop asked by mic / end takes 6–9 ms in the browser; true barge-in needs day 3's VAD | ≤ 350 ms |
| AC-11.3 **[GATE]** | ⬜ Premature cut-off rate | < 3% |
| AC-11.4 **[GATE]** | ⬜ ASR WER gap between accent groups | ≤ 8 points |
| AC-11.5 | ⬜ Overall WER on pilot audio | ≤ 12% |
| AC-11.6 | ⬜ "It kept cutting me off" complaints | < 5% of sessions |
| AC-11.7 | ⬜ Prefill cancel rate | 25–40% (outside → tune the window) |
| AC-11.8 | ⬜ Voice session completion rate vs text | within 10 points |
| AC-11.9 | ⬜ Push-to-talk fallback engages before abandonment | ≥ 80% of poor-network sessions |

---

## 4. Edge cases

Spec §12. Listed in full, because several are one afternoon each and are the
difference between a demo and a product.

| EC | | Expected behaviour |
|---|---|---|
| EC-11.1 | ⬜ Candidate speaks over the very first word | Barge-in works from t=0; question re-offered ("go ahead") |
| EC-11.2 | ⬜ Two people speaking (roommate) | Diarisation flags a second speaker → M18 signal; interviewer continues with the enrolled speaker |
| EC-11.3 | ⬜ Candidate silent for 45 s | One prompt, then a second, then offer to move on |
| EC-11.4 | ⬜ Extremely fast speaker | Adaptive threshold shortens; ASR handles it; no change needed |
| EC-11.5 | ⬜ Very slow / halting speaker | Threshold lengthens to the 1,400 ms cap; semantic endpointing does the rest |
| EC-11.6 | ⬜ Heavy background noise (hostel) | Noise suppression + raised VAD threshold from mic-check floor; suggest headphones once |
| EC-11.7 | ⬜ Candidate uses a Bluetooth headset that cuts the first 200 ms | Known issue; prefix padding + a mic-check warning if detected |
| EC-11.8 | ⬜ Echo (speakers, no headphones) | AEC handles most; if self-transcription detected, prompt for headphones |
| EC-11.9 | ⬜ ASR returns empty for a long utterance | Ask to repeat; if it happens twice, switch to text |
| EC-11.10 | ⬜ Candidate answers entirely in Hindi | Transcribed and scored on content; noted in the report, never penalised |
| EC-11.11 | ⬜ TTS mispronounces a technical term | Lexicon override table (`Kubernetes` → phonemes); crowd-flaggable |
| EC-11.12 | ⬜ Phone call interrupts on mobile | Auto-pause, resume with a 5-second re-entry |
| EC-11.13 | ⬜ Tab backgrounded | Audio continues (WebRTC), but warn — students do this and then miss the question |
| EC-11.14 | ⬜ Barge-in immediately after the interviewer's first syllable | Treated as an interruption, not a false positive (250 ms sustain requirement handles it) |
| EC-11.15 | ⬜ Network dies mid-answer | Local recording buffer flushed on reconnect; nothing lost |

---

## 5. Data model

Spec §5 declares 7 types. None exist.

| Type | | |
|---|---|---|
| `AudioSessionConfig` | ⬜ | Not written |
| `VADState` | ⬜ | Not written |
| `TranscriptWord` | ⬜ | Not written |
| `ASRResult` | ⬜ | Not written |
| `UtteranceCompleteness` | ⬜ | Not written |
| `TTSRequest` | ⬜ | Not written |
| `TurnTiming` | 🟡 | The browser's marks and §11's stages (`m11_line_timing`, `ledger.py`); `vad_decision` and `asr_final` wait for days 3–4 |

---

## 6. Deferred — inter-module

Not gaps in this module. Each needs a module that is not built or not wired
yet, and each is listed so it is not mistaken for an oversight.

**The voice client is in `@ai/core`** (v0.14.0, day 1) — M11's code, there
because M06 and M11 both use it and M14 will. Changes to it are planned here and
released as core versions; each consumer bumps its pin when ready. M06's
`speech.ts` (browser recognition) stays M06's until day 4's ASR route.

The spec names **M12, M13, M14, M18**. Until those are wired, anything
depending on them is blocked rather than unstarted, and the distinction
matters: one is work waiting to be done and the other is work that cannot
begin.

---

## 7. First moves

When work begins, the order that has worked on M01 and M02:

1. **The manifest and the ports.** `module.json` with `depends_on` declaring
   every upstream as OPTIONAL, each with an `on_missing` sentence a student
   can act on. Rule 2: a missing dependency narrows scope, never quality, and
   never silently.
2. **Identity before endpoints.** Router-level `enforce_access` on
   `ai_core.identity`, so no route can be written without it. A per-route
   check is the one somebody omits on the sixteenth endpoint, and the
   sixteenth endpoint is the one that leaks.
3. **The P0 that carries the module's name**, not the easiest one.
4. **Contract gates from the first commit** — every route has a client, every
   hook has a screen, every response field is declared on the frontend. M01
   shipped ten routes nobody could reach before these existed.
5. **A golden corpus before the third extraction fix**, not after. On M02 it
   found four real bugs within an hour of existing.

### Revision 2 build order (2026-10-05)

Replaces the spec's Revision 1 order (§14), which starts at the media worker
Revision 2 removes. Days are the spec's unit — a focused day each.

| Day | Task |
|---|---|
| 1 | ✅ Repo scaffold — `module.json`, ports from PORTS.txt, identity — and M06's `voice-core.ts` / `voice.ts` as the client baseline (moved to `@ai/core` v0.14.0; the voice check at `/voice`) |
| 2 | ✅ The latency ledger (`TurnTiming`) in the browser from day one; measure M06's browser voice honestly: first audio after a line lands, stop time after the mic (Core v0.15.0, M11 `1f8ffe1`; p95 answer → audio 1.41 s, cold start 2–3 s, stop 6–9 ms) |
| 3 | ✅ Barge-in (2026-10-06): §6.5's energy rule in the browser (`vad.ts`, `useListening`), the stop chain (`bargeIn`), Final Boss's contest, the ledger's `barge_in` stage; 261 ms measured live (Core v0.18.1, M11 `0257db8`, M06 `cc4619c`). Silero moves to day 5 |
| 4 | ASR route on Groq `whisper-large-v3-turbo` with word timestamps (confirm the API returns word granularity); browser recognition stays as the no-key fallback |
| 5 | Smart Turn v3.2 for semantic endpointing, with the adaptive VAD threshold (FR-11.4, FR-11.5); checked on 200 labelled endings of real answers |
| 6 | Accent WER on the Svarah benchmark across the ASR candidates (AC-11.4); choose by the number |
| 7 | ✅ (pulled forward, 2026-10-06) TTS tier 1 is **Chatterbox Turbo via ONNX on the server**, cast per persona and cached (M11 `2aed9bb`, `90063c9`) — the blind listening test's choice, replacing Kokoro. Still open from this row: clause-level streaming (FR-11.7) and the lexicon (EC-11.11) |
| 8 | TTS tier 2 behind a flag: Groq Orpheus streaming; first-audio p95 against tiers 0 and 1 |
| 9 | `heard_up_to_ms` truncation (FR-11.9), repeat from cache (FR-11.13), clarification on low confidence (FR-11.15, FR-11.16) |
| 10 | Mic check with a live transcription round trip and a noise floor (FR-11.2); echo detection (EC-11.8) |
| 11 | Calibrated silence, backchannels and note-taking pauses from the persona files (FR-11.10 to FR-11.12) |
| 12 | Per-turn audio stored with consent, aligned to the transcript clock (FR-11.19); the push-to-talk ladder (FR-11.17) |
| 13 | The face — only if chosen (spec §15.6): lip-sync from the audio itself (HeadAudio or `wav2arkit`) |
| 14 | Latency harness (nightly), device matrix including the Arc through OpenVINO, network chaos |
