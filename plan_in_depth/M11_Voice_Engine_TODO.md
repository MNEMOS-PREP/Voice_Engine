# M11 — TODO · Voice & Conversation Engine

> **Completion: 0%** — 0 of 22 functional requirements met. **No code yet** — the `Voice_Engine` repo holds only this plan. Since 2026-10-05 M06 carries an interim browser voice in both directions (§1b); it is M06's code and is not counted here. The spec has a Revision 2 (§0 of the spec): browser-first and free. The requirement count is the spec's own, so this is a measure of scope ahead rather than of progress behind.
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
| Status | **Not started.** No code exists — no backend, no frontend, no tests. |
| Spec | Written, and the source of every row below. |
| Scope | 22 functional requirements (18 of them P0), 9 acceptance metrics (4 release-blocking), 15 edge cases. |

### 1b. What M06 already carries (interim — counted in M06, not here)

| FR | What M06 does since 2026-10-05 | |
|---|---|---|
| FR-11.3 | Browser recognition in en-IN: final phrases into the answer box; no word timestamps | 🟡 interim |
| FR-11.7 | The line read aloud after it lands, a sentence at a time — not a streamed first clause | 🟡 interim |
| FR-11.8 | The voice stops when the mic button is pressed — no VAD, not measured | 🟡 interim |
| FR-11.13 | "Repeat the question" says it again, interrupting | 🟡 interim |
| FR-11.18 | The room is text-first: every spoken line is on screen | ✅ in M06 |
| FR-11.21 | One voice per persona from its `voice_id`, paced by its manner; Edge has two neural en-IN voices, so personas of a kind share one | 🟡 interim |

Everything below is ⬜ because nothing is built. That is the honest state and
it is worth writing down rather than leaving three sections saying
_To fill in._ — the point of this list is that the next session can start from
it instead of re-reading a six-hundred-line spec.

---

## 2. Functional requirements

Spec §4, verbatim. This is the authoritative list.

| FR | | Priority |
|---|---|---|
| FR-11.1 | ⬜ WebRTC audio capture with echo cancellation and noise suppression | P0 |
| FR-11.2 | ⬜ Real mic check with a live transcription round-trip | P0 |
| FR-11.3 | ⬜ Streaming ASR with word-level timestamps | P0 |
| FR-11.4 | ⬜ VAD-based endpointing with a per-speaker adaptive threshold | P0 |
| FR-11.5 | ⬜ Semantic endpointing to avoid cutting incomplete utterances | P0 |
| FR-11.6 | ⬜ Speculative LLM prefill on stabilised partial transcripts | P1 |
| FR-11.7 | ⬜ Streaming TTS with clause-level first chunk | P0 |
| FR-11.8 | ⬜ Barge-in: full stop of LLM + TTS + playback within 350 ms | P0 |
| FR-11.9 | ⬜ Truncate the interviewer turn at `heard_up_to_ms` on barge-in | P0 |
| FR-11.10 | ⬜ Calibrated silence per persona/mode with no UI change | P0 |
| FR-11.11 | ⬜ Backchannels on a separate bus, disabled in Final Boss | P1 |
| FR-11.12 | ⬜ Note-taking pauses | P1 |
| FR-11.13 | ⬜ Repeat-last-utterance from cache | P0 |
| FR-11.14 | ⬜ Mid-turn modality switch preserving the partial transcript | P0 |
| FR-11.15 | ⬜ Low-confidence spans marked and excluded from evidence citation | P0 |
| FR-11.16 | ⬜ Natural clarification behaviour on low ASR confidence | P1 |
| FR-11.17 | ⬜ Bandwidth degradation ladder down to push-to-talk | P0 |
| FR-11.18 | ⬜ Live captions always on | P0 |
| FR-11.19 | ⬜ Per-turn audio stored, aligned to the transcript clock | P0 |
| FR-11.20 | ⬜ p95 end-of-speech → first audio byte < 1.2 s | P0 |
| FR-11.21 | ⬜ Distinct voice per persona; no cloning of real people | P0 |
| FR-11.22 | ⬜ Code-switch tolerance without penalty | P0 |

---

## 3. Acceptance gates

Spec §13. A **[GATE]** is release-blocking; the rest are tracked.

| AC | | Target |
|---|---|---|
| AC-11.1 **[GATE]** | ⬜ p95 end-of-speech → first audio | ≤ 1.2 s |
| AC-11.2 **[GATE]** | ⬜ Barge-in stop | ≤ 350 ms |
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
| `TurnTiming` | ⬜ | Not written |

---

## 6. Deferred — inter-module

Not gaps in this module. Each needs a module that is not built or not wired
yet, and each is listed so it is not mistaken for an oversight.

**M06 carries M11's interim voice** (§1b). When M11 starts it takes
`voice-core.ts` and `voice.ts` as its client baseline; when a second module
needs them (M14's GD room), they graduate to Platform_Core rather than being
copied — the rule M01's client states for verbs core does not carry.

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
| 1 | Repo scaffold — `module.json`, ports from PORTS.txt, identity — and M06's `voice-core.ts` / `voice.ts` as the client baseline |
| 2 | The latency ledger (`TurnTiming`) in the browser from day one; measure M06's browser voice honestly: first audio after a line lands, stop time after the mic |
| 3 | Browser VAD (Silero via `ricky0123/vad`): the student starting to speak stops playback client-side, and the server is told to cancel |
| 4 | ASR route on Groq `whisper-large-v3-turbo` with word timestamps (confirm the API returns word granularity); browser recognition stays as the no-key fallback |
| 5 | Smart Turn v3.2 for semantic endpointing, with the adaptive VAD threshold (FR-11.4, FR-11.5); checked on 200 labelled endings of real answers |
| 6 | Accent WER on the Svarah benchmark across the ASR candidates (AC-11.4); choose by the number |
| 7 | TTS tier 1: Kokoro via HeadTTS, opt-in and cached; clause-level streaming (FR-11.7); the `voice_id` → per-tier voice map; the lexicon (EC-11.11) grown from `voice-core.ts`'s table |
| 8 | TTS tier 2 behind a flag: Groq Orpheus streaming; first-audio p95 against tiers 0 and 1 |
| 9 | `heard_up_to_ms` truncation (FR-11.9), repeat from cache (FR-11.13), clarification on low confidence (FR-11.15, FR-11.16) |
| 10 | Mic check with a live transcription round trip and a noise floor (FR-11.2); echo detection (EC-11.8) |
| 11 | Calibrated silence, backchannels and note-taking pauses from the persona files (FR-11.10 to FR-11.12) |
| 12 | Per-turn audio stored with consent, aligned to the transcript clock (FR-11.19); the push-to-talk ladder (FR-11.17) |
| 13 | The face — only if chosen (spec §15.6): lip-sync from the audio itself (HeadAudio or `wav2arkit`) |
| 14 | Latency harness (nightly), device matrix including the Arc through OpenVINO, network chaos |
