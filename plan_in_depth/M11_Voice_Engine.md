# M11 — Voice & Conversation Engine

> **Master plan reference:** §37 · **Phase:** 3 · **Owner:** E2 · **Depends on:** M6 · **Feeds:** M12, M13, M14
> **Everything about realism lives or dies here. This is a latency-engineering module.**

---

## 0. Revision 2 (2026-10-05) — browser-first, and free

Revision 1 (below, unchanged) assumed a media worker with a GPU, a managed
voice API as the primary voice, and a completeness classifier we would label
and train ourselves. Three things changed that:

- **The constraint is now explicit: free, no paid API required.** The platform
  is a final-year project run on students' own laptops and the team's — the
  development laptop has an Intel Arc A370M (4 GB, no CUDA) beside its Iris Xe.
- **The browsers already do half the job.** Microsoft Edge ships neural
  Indian-English voices in its built-in speech synthesis — "Microsoft Neerja /
  Prabhat Online (Natural) - English (India)", plus Hindi, Bengali, Gujarati and
  Kannada — free, verified in a headless Edge on 2026-10-04 (321 voices).
  Windows has its own Indian-English voices (Heera, Ravi) that Chrome lists
  too; Safari on a Mac has Veena and Rishi.
- **The open-source field moved.** A sweep of ~480 GitHub repositories on
  2026-10-04 (faces, TTS, ASR, voice-agent frameworks, AI interviewers) found
  free, licensed, maintained answers to the parts Revision 1 planned to build or
  buy — listed with their licences in the TODO's §0.

**M06 already carries the first slice (2026-10-05).** The interviewer reads each
line of record aloud in the voice its persona file names (`voice_id`,
`en-IN-female-warm`), the drawn face's mouth moves with each word, the voice
stops when the mic opens, and the browser's own recognition (en-IN) takes the
spoken answer. M11 absorbs that code when it starts; it is the baseline every
latency number below has to beat.

### What Revision 2 changes

| § | Revision 1 | Revision 2 | Why |
|---|---|---|---|
| 6.1 Transport | WebRTC to a media worker from day 1 | VAD and playback **in the browser**; utterance audio to the server over a WebSocket. WebRTC (an SFU — LiveKit, Apache-2.0) when M14's multi-party GD needs it | No GPU server; a barge-in stop that never crosses the network |
| 6.2/6.3 Endpointing | Silero VAD + a completeness classifier we label (2,000 endings) and train | Silero VAD in the browser (`ricky0123/vad`, ISC) + **Smart Turn v3.2** (Pipecat, BSD-2 code and weights, 8 MB, ~10–65 ms on a CPU, 23 languages incl. English and Hindi) | Trained and open; day 8 becomes "evaluate on our answers", not "train" |
| 6.6 TTS | Managed primary, Piper fallback | **Tiers:** (0) browser voices — shipping; (1) Kokoro-82M (Apache-2.0) in the browser via `kokoro-js` / HeadTTS (MIT; word timestamps and visemes), opt-in because the model is a 90–330 MB download; (2) managed streaming for latency — Groq Orpheus on the keys we hold ($22 per 1M chars), Cartesia / Deepgram if first-audio time demands | Free first; Piper moved to `piper1-gpl` (GPL-3.0); managed voices have no Indian-English voice, so tier 0 stays the Indian one |
| 6.7 ASR | Streaming `faster-whisper` large-v3 on the media worker | Browser recognition (en-IN) as the interim; **Groq `whisper-large-v3-turbo`** as primary (free tier: 2,000 requests/day, 7,200 audio-seconds/hour; then $0.04/hour); `faster-whisper` / `whisper.cpp` locally as the fallback; WhisperX alignment offline for M12's word timings | large-v3 in real time needs a GPU we do not have; Groq's free tier covers a cohort's practice |
| 6.7 Accent | "Accent-robust ASR" | **Measured, not assumed:** WER by accent group on the Svarah benchmark (9.6 h of Indian-accented English, 117 speakers) for browser en-IN, Groq Whisper, local Whisper, Oriserve's Indian-English Whisper fine-tune and Vosk `en-in` (Apache-2.0; WER 36–49 on NPTEL, likely weakest). AC-11.4 picks the winner | AC-11.4 is a gate; a choice made by reputation would fail it silently |
| 14 Build order | 14 days from the media worker up | The TODO's §7 order, starting from what M06 ships | Day 1 of Revision 1 is the part Revision 2 removes |
| 15.1 | Managed vs self-hosted — open | Resolved: tiers above | |
| 15.6 | — | **A face for the interviewer** — the user's decision; options below | M06's open question 1 sends it here for the mechanics |

**Unchanged:** every functional requirement, every gate, the latency ledger,
one voice per persona, **no cloning of real people**, voices disclosed as AI on
the consent screen, captions always on.

**One finding for M12 and M17, recorded here because it comes from the voice
path:** recognisers delete filler words (M12's Trap 1) — the browser's does too,
so M06's live filler count is a floor, not a measure. Verbatim transcription is
M12's to choose; this sweep did not cover it.

---

## 1. In one paragraph

Interviews are spoken, and spoken interaction is a timing problem before it is an AI problem. This module owns the full duplex loop: capture audio, decide when the candidate has finished speaking, transcribe with word-level timestamps, get a response streaming out of the model, speak it in a distinct persona voice, and — critically — stop talking within 350 ms when the candidate starts. It also owns the deliberate *non*-speech: the calibrated silence after an answer, the note-taking pause, the backchannel "mm-hm". Get the timing right and the interview feels real. Get it wrong by 500 ms and it feels like a phone call to a call centre.

---

## 2. Reverse-thinking: the user

### 2.1 The three complaints that mean we failed

| Complaint | Actual cause | Fix |
|---|---|---|
| *"It kept cutting me off"* | Endpointing fired on a mid-thought pause | Semantic endpointing (§6.3) |
| *"It took forever to respond"* | Serial pipeline, no streaming, no prefill | Streaming + speculative prefill (§6.4) |
| *"It didn't hear me properly"* | Mic setup, or accent handling | Real mic check + accent-robust ASR + clarification behaviour |

All three are timing/perception failures, not intelligence failures. A student will forgive a mediocre question asked with perfect timing long before they'll forgive a brilliant question that arrived 3 seconds late.

### 2.2 The rhythm we're reproducing

Real interview timing, measured from recordings:

```
Candidate finishes ─┬─ 300–900 ms ─┬─ interviewer starts
                    │              │
                    └─ sometimes 2–5 s of deliberate silence
                       (thinking, note-taking, or pressure)

Interviewer speaking ─── candidate interrupts ─── interviewer stops in ~200–400 ms
```

So our targets aren't "as fast as possible" — they're **human-plausible**. A 200 ms response is uncanny; 800 ms is natural; 2,500 ms is broken.

### 2.3 The mic check (build this properly — it prevents most support tickets)

```
┌───────────────────────────────────────────────────────────┐
│  Quick sound check                                        │
│                                                           │
│  Input:  [ MacBook Pro Microphone ▾ ]                     │
│                                                           │
│  Say something — anything, five seconds.                  │
│                                                           │
│     ▁▂▃▅▇▇▅▃▂▁▂▃▅▇                                        │
│     ● Good level                                          │
│                                                           │
│  I heard: "testing one two three"                         │
│                                                           │
│  ⚠ There's some background noise. It'll still work, but   │
│    a quieter room helps.                                  │
│                                                           │
│  [ ▶ Play it back ]              [ Sounds right → ]       │
└───────────────────────────────────────────────────────────┘
```

It must **actually transcribe** the test phrase and show it. A level meter alone doesn't catch "the browser is using the wrong device" or "the ASR can't handle this accent+noise combination", which are the two real failure causes.

Noise floor is measured here and stored — it calibrates VAD thresholds for the session, which materially improves endpointing in a noisy hostel room.

### 2.4 The controls during the interview

- **`↻ Repeat that`** — replays the last utterance (cached audio, instant). Used constantly. Its absence causes fake answers.
- **`💬 Type instead`** — switches modality mid-turn, keeping the partial transcript.
- **Live captions, always on.** Not an accessibility afterthought — everyone reads along, especially on a noisy campus, and it also lets students catch ASR errors themselves.
- **`⚑ It misheard me`** — one tap, flags the turn, and the interviewer offers to re-ask. Cheap, and it gives us labelled ASR failures for free.

### 2.5 What silence must feel like

```
Candidate: "...so I'd use a hash map, I think."
[1.4 s of nothing — no spinner, no "thinking...", no sound]
Interviewer: "Mm. What makes you say 'I think'?"
```

**During deliberate silence, the UI must show nothing changing.** A spinner during a calibrated pause converts a meaningful interviewer behaviour into a perceived bug. The only exception: if silence exceeds 4 s for a *technical* reason (not a deliberate one), a subtle indicator appears — because at that point it *is* a bug and pretending otherwise is worse.

---

## 3. Reverse-thinking: the developer

### 3.1 The seven traps

**Trap 1 — Serial pipeline.** `wait_for_silence() → transcribe() → llm() → tts() → play()` gives ~3.5 s. Every stage must overlap. *Counter: streaming everywhere + speculative prefill (§6.4).*

**Trap 2 — Fixed silence threshold for endpointing.** 700 ms works for a fast speaker and butchers a slow one. And it *always* cuts off "the complexity is... O of..." *Counter: per-speaker adaptive threshold + semantic completeness classifier (§6.3).*

**Trap 3 — Barge-in that only stops the audio.** Stopping playback but continuing to generate/stream means the interviewer resumes mid-sentence 2 seconds later. *Counter: barge-in cancels the LLM stream, the TTS stream, and the playback buffer, and truncates the transcript at the point actually heard (§6.5).*

**Trap 4 — Transcribing what the candidate heard vs what we said.** If we were interrupted at word 12 of 30, the candidate answered a *shorter* question. Scoring against the full question is unfair. *Counter: record `heard_up_to_ms` and truncate the interviewer turn in the transcript.*

**Trap 5 — Echo.** Without echo cancellation, the ASR transcribes the interviewer's own TTS as candidate speech and the system talks to itself. *Counter: `echoCancellation: true` on `getUserMedia`, plus a server-side guard that ignores ASR output during TTS playback windows unless energy exceeds the barge-in threshold.*

**Trap 6 — Ignoring Indian English.** Off-the-shelf ASR on Indian-accented technical speech gives WER in the 20–30% range without adaptation, and "Bhattacharya" becomes "but a charter". *Counter: hotword biasing, domain lexicon, accent evaluation as a release gate, and LoRA adaptation on consented pilot audio (§6.7).*

**Trap 7 — Treating code-switching as an error.** Hinglish is normal. `"toh basically main hash map use karunga"` is a competent answer. *Counter: code-switch tolerant decoding, and content scoring that never penalises language mixing (M13 rule).*

### 3.2 The non-obvious hard parts

1. **WebRTC vs WebSocket.** WebRTC gives you echo cancellation, jitter buffering, and adaptive bitrate for free. Raw WS + `MediaRecorder` gives you control but you rebuild all of that badly. **Use WebRTC for audio transport**, WS for control/events.
2. **First-audio latency is dominated by TTS chunking.** If the first TTS chunk is a whole sentence, you wait for the whole sentence. Chunk at the first clause boundary (~6–10 words).
3. **Speculative prefill wastes tokens.** Starting the LLM on a partial transcript and cancelling costs money. Budget it: cancel-rate × cost. Worth it — but measure it.
4. **Mobile Safari.** Autoplay policies, audio-session interruptions from phone calls, and background-tab throttling all break voice. Test on a real iPhone early.
5. **The audio must be stored for M12 and evidence.** Aligned, per-turn, with the same clock as the transcript. Getting the clocks aligned across ASR, TTS, and the UI is fiddly and must be designed, not discovered.

---

## 4. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-11.1 | WebRTC audio capture with echo cancellation and noise suppression | P0 |
| FR-11.2 | Real mic check with a live transcription round-trip | P0 |
| FR-11.3 | Streaming ASR with word-level timestamps | P0 |
| FR-11.4 | VAD-based endpointing with a per-speaker adaptive threshold | P0 |
| FR-11.5 | Semantic endpointing to avoid cutting incomplete utterances | P0 |
| FR-11.6 | Speculative LLM prefill on stabilised partial transcripts | P1 |
| FR-11.7 | Streaming TTS with clause-level first chunk | P0 |
| FR-11.8 | Barge-in: full stop of LLM + TTS + playback within 350 ms | P0 |
| FR-11.9 | Truncate the interviewer turn at `heard_up_to_ms` on barge-in | P0 |
| FR-11.10 | Calibrated silence per persona/mode with no UI change | P0 |
| FR-11.11 | Backchannels on a separate bus, disabled in Final Boss | P1 |
| FR-11.12 | Note-taking pauses | P1 |
| FR-11.13 | Repeat-last-utterance from cache | P0 |
| FR-11.14 | Mid-turn modality switch preserving the partial transcript | P0 |
| FR-11.15 | Low-confidence spans marked and excluded from evidence citation | P0 |
| FR-11.16 | Natural clarification behaviour on low ASR confidence | P1 |
| FR-11.17 | Bandwidth degradation ladder down to push-to-talk | P0 |
| FR-11.18 | Live captions always on | P0 |
| FR-11.19 | Per-turn audio stored, aligned to the transcript clock | P0 |
| FR-11.20 | p95 end-of-speech → first audio byte < 1.2 s | P0 |
| FR-11.21 | Distinct voice per persona; no cloning of real people | P0 |
| FR-11.22 | Code-switch tolerance without penalty | P0 |

---

## 5. Data contracts

```python
class AudioSessionConfig(BaseModel):
    sample_rate: int = 16000
    codec: Literal["opus"] = "opus"
    frame_ms: int = 20
    echo_cancellation: bool = True
    noise_suppression: bool = True
    auto_gain: bool = True
    noise_floor_db: float          # measured at mic check
    vad_threshold: float           # derived from noise floor

class VADState(BaseModel):
    speaking: bool
    speech_started_ms: int | None
    last_speech_ms: int
    silence_ms: int
    adaptive_threshold_ms: int     # per-speaker, updated during the session

class TranscriptWord(BaseModel):
    word: str
    start_ms: int
    end_ms: int
    confidence: float
    is_filler: bool | None         # set later by M12

class ASRResult(BaseModel):
    turn_id: UUID
    text: str
    words: list[TranscriptWord]
    is_final: bool
    mean_confidence: float
    low_confidence_spans: list[tuple[int,int]]
    detected_languages: list[str]  # ["en","hi"] for code-switching
    audio_uri: str

class UtteranceCompleteness(BaseModel):
    score: float                   # 0–1, is this a complete thought?
    reason: Literal["syntactic_complete","trailing_conjunction","mid_clause",
                    "filled_pause_final","list_continuation"]
    extend_silence_by_ms: int

class TTSRequest(BaseModel):
    text: str
    voice_id: str
    speed: float
    pauses: list[tuple[int,int]]   # SSML-style pause insertions (char_pos, ms)
    persona_id: str

class TurnTiming(BaseModel):
    """The latency ledger — logged for every turn."""
    speech_end_ms: int
    vad_decision_ms: int
    asr_final_ms: int
    llm_first_token_ms: int
    tts_first_audio_ms: int
    playback_start_ms: int
    total_ms: int
    prefill_used: bool
    prefill_cancelled: bool
    barge_in_at_ms: int | None
    heard_up_to_ms: int | None
```

---

## 6. The pipeline in minute detail

### 6.1 Transport
```
Browser ──WebRTC (Opus 16k, 20ms)──► SFU/direct ──► media worker
        ◄─WebRTC audio──────────────────────────── TTS stream
        ◄─WebSocket (control/events/captions)────► session service
```
WebRTC handles echo cancellation, jitter, and packet loss concealment. The WS carries `question.asked`, `listening.started`, caption deltas, and control commands.

### 6.2 VAD & endpointing
**Silero VAD**, 30 ms frames, on the media worker (not the browser — we want the same VAD behaviour everywhere).

```python
adaptive_threshold_ms = clamp(
    base=550,
    adjusted = 550 + 1.2 * (speaker_mean_intra_pause_ms - 250),
    lo=400, hi=1400
)
# A speaker whose natural mid-sentence pauses average 500 ms gets ~850 ms
```
`speaker_mean_intra_pause_ms` is estimated over the session's first 3 turns and updated continuously. This one adaptation removes most "it cut me off" complaints on its own.

### 6.3 Semantic endpointing
When VAD says silence has reached the threshold, run a fast completeness check before committing:

```
Cheap classifier (distilled, ~15 ms, runs locally on the partial transcript):
  ends with conjunction/preposition ("and", "because", "so", "the", "of")   → +600 ms
  ends with a filled pause ("um", "uh")                                     → +500 ms
  ends mid-list ("first, ... second, ...")                                  → +800 ms
  syntactically complete sentence                                           → commit now
  ends with a trailing "I think" / "right?"                                 → commit now
Cap total extension at 1,500 ms; never wait more than 2.5 s total.
```
Implementation: a small classifier over POS tags + last-token lexicon, trained on 2,000 hand-labelled utterance endings from our own recordings. **Do not use an LLM call here** — it's on the hot path and 15 ms vs 400 ms is the whole game.

### 6.4 Speculative prefill
```
partial transcript stabilises (no change for 250 ms, ≥8 words)
  → fire the LLM request with the partial
  → keep streaming ASR
  → if the final transcript differs materially (edit distance > 15% of length):
        cancel, re-fire with the final          [prefill_cancelled = true]
    else:
        continue the in-flight stream           [saves ~400 ms]
```
Measured cancel rate should sit around 25–35%. Net saving ≈ 250–350 ms per turn at a cost of ~0.3× extra input tokens on cancelled turns. Track `prefill_cancelled` rate; if it exceeds 50%, the stabilisation window is too short.

### 6.5 Barge-in
```
VAD detects candidate speech during TTS playback
  energy > (noise_floor + 12 dB) sustained 250 ms
    → t0: stop feeding the playback buffer, duck over 80 ms
    → t0+30ms: cancel the TTS HTTP/WS stream
    → t0+50ms: cancel the LLM generation
    → t0+120ms: flush the playback buffer
    → total stop ≤ 350 ms
    → record heard_up_to_ms = playback position at t0
    → truncate the interviewer transcript at the word covering that position
    → mark turn.completion_reason = "barge_in"
```
**In Final Boss mode**, the interviewer may *contest* a barge-in once per round — it continues for 1.5 s more before yielding ("—if I could just finish the question—"). This is realistic senior-interviewer behaviour, it is uncomfortable, and it is exactly what Final Boss is for. Never in other modes.

### 6.6 TTS
- Primary: a low-latency managed streaming voice API, one `voice_id` per persona.
- First chunk cut at the first clause boundary or 10 words, whichever is sooner → first audio in ~200 ms.
- SSML pauses inserted from persona parameters (a `methodical_engineer` gets 350 ms after a question; an `impatient_senior` gets 80 ms).
- Cached: greetings, transitions, backchannels, and the last utterance (for `Repeat that`) — cache hit is instant.
- Self-hosted fallback: **Piper** (fast, small, adequate) on the media worker. Quality drops audibly; a banner says "voice quality reduced".
- **No voice cloning of real people.** Persona voices are synthetic and are disclosed as AI in the consent screen.

### 6.7 ASR for Indian English
- `faster-whisper` large-v3, INT8, streaming wrapper with a 5-second rolling window + 1-second stride.
- **WhisperX forced alignment** for word timings — required by M12 (fillers, pauses) and by evidence citation.
- **Hotword biasing:** an initial prompt containing the session's technical lexicon (concepts from the current round) plus Indian name patterns. This measurably fixes "Kubernetes"/"Bhattacharya" class errors.
- **Code-switch:** language detection per segment; Hindi/Tamil/Telugu segments transcribed in-language and retained as-is in the transcript with a language tag. M13 is instructed to score content, not language.
- **Evaluation gate:** WER measured separately per accent group on our own pilot recordings, reported honestly, and a gap > 8 points between groups is a release blocker (fairness, not just quality).
- **Phase-4 adaptation:** LoRA fine-tune on consented pilot audio; compare against baseline and report.

### 6.8 Clarification behaviour
```
if final transcript has a low-confidence span overlapping a decisive term:
    interviewer asks a natural clarifier:
      "Sorry — did you say *quick* sort or *quick select*?"
    (max once per turn, max 3 per session — beyond that it's annoying)
    mark the span excluded from evidence citation regardless
```

### 6.9 Degradation ladder
| Condition | Action |
|---|---|
| Bandwidth < 100 kbps | Opus 8 kHz mono; disable ambient bed; larger TTS chunks |
| Packet loss > 5% sustained | Warn once; increase jitter buffer |
| Packet loss > 15% or 2 disconnects | **Switch to push-to-talk**: record locally → upload → respond. Turn-based but fully functional |
| Mic unavailable | Text mode; delivery scoring omitted and marked absent |
| TTS fails | Text render + "audio's having trouble" note |
| ASR fails twice | Auto-switch to text |

**Push-to-talk is not a degraded experience to be ashamed of.** For a student on 3G in a hostel, it is the difference between using the product and not. Design it properly: a big hold-to-talk button, a visible upload progress, and the same interviewer behaviour.

---

## 7. API surface

```
POST /v1/voice/session                 → ICE config, session token
WS   /v1/voice/{session_id}/control    events + captions
     (media over WebRTC)
POST /v1/voice/mic-check               {audio_blob} → {transcript, level, noise_floor}
POST /v1/voice/{session_id}/repeat     → cached audio URI
POST /v1/voice/{session_id}/ptt        push-to-talk upload
POST /v1/voice/{turn_id}/misheard      flag
GET  /v1/voice/{turn_id}/audio         signed URL, consent-checked
GET  /v1/voice/{session_id}/timings    TurnTiming[] (internal metrics)
```

---

## 8. UI specification

**Components:** `MicCheck` · `AudioMeter` · `CaptionStream` (live, word-by-word) · `SpeakingIndicator` · `ListeningIndicator` · `PushToTalkButton` · `RepeatButton` · `MishearFlag` · `ConnectionQualityBadge` · `ModalitySwitch`

**States:**

| State | Visual | Sound | Duration |
|---|---|---|---|
| Interviewer speaking | avatar ring animates with amplitude | TTS | — |
| Listening | live waveform | — | — |
| Processing (< 800 ms) | nothing changes | — | — |
| Processing (> 800 ms) | subtle three-dot | — | — |
| **Deliberate silence** | **nothing changes** | — | 1.2–4.5 s |
| Technical stall (> 4 s) | "one moment…" | — | — |
| Barge-in accepted | ring dims sharply | audio ducks | 80 ms |
| Poor connection | amber badge | — | — |
| Push-to-talk mode | large hold button | — | — |

**Captions:** rendered word-by-word as ASR partials arrive, with low-confidence words in a lighter weight (a visual cue that "I might have misheard this"). Final transcript replaces partials cleanly without reflow jitter.

**Accessibility:** captions are the primary channel for deaf/HoH users and are always on; the full text mode is a first-class equivalent, not a fallback; all audio state changes announced via ARIA live; `prefers-reduced-motion` disables amplitude animation.

**Mobile:** portrait-optimised; handles audio interruption (incoming call) by auto-pausing the session and resuming cleanly; keeps the screen awake during a session.

---

## 9. Edge cases

| ID | Case | Behaviour |
|---|---|---|
| EC-11.1 | Candidate speaks over the very first word | Barge-in works from t=0; question re-offered ("go ahead") |
| EC-11.2 | Two people speaking (roommate) | Diarisation flags a second speaker → M18 signal; interviewer continues with the enrolled speaker |
| EC-11.3 | Candidate silent for 45 s | One prompt, then a second, then offer to move on |
| EC-11.4 | Extremely fast speaker | Adaptive threshold shortens; ASR handles it; no change needed |
| EC-11.5 | Very slow / halting speaker | Threshold lengthens to the 1,400 ms cap; semantic endpointing does the rest |
| EC-11.6 | Heavy background noise (hostel) | Noise suppression + raised VAD threshold from mic-check floor; suggest headphones once |
| EC-11.7 | Candidate uses a Bluetooth headset that cuts the first 200 ms | Known issue; prefix padding + a mic-check warning if detected |
| EC-11.8 | Echo (speakers, no headphones) | AEC handles most; if self-transcription detected, prompt for headphones |
| EC-11.9 | ASR returns empty for a long utterance | Ask to repeat; if it happens twice, switch to text |
| EC-11.10 | Candidate answers entirely in Hindi | Transcribed and scored on content; noted in the report, never penalised |
| EC-11.11 | TTS mispronounces a technical term | Lexicon override table (`Kubernetes` → phonemes); crowd-flaggable |
| EC-11.12 | Phone call interrupts on mobile | Auto-pause, resume with a 5-second re-entry |
| EC-11.13 | Tab backgrounded | Audio continues (WebRTC), but warn — students do this and then miss the question |
| EC-11.14 | Barge-in immediately after the interviewer's first syllable | Treated as an interruption, not a false positive (250 ms sustain requirement handles it) |
| EC-11.15 | Network dies mid-answer | Local recording buffer flushed on reconnect; nothing lost |

---

## 10. Failure modes & fallbacks

| Failure | Fallback | User sees |
|---|---|---|
| ASR service down | Local `faster-whisper` on the media worker (already primary) → managed API as backup | Nothing |
| Both ASR paths down | Push-to-talk with delayed transcription, or text mode | "Switching to typing for now" |
| TTS down | Piper local → text render | "Voice quality reduced" or text |
| WebRTC fails to connect | WS + `MediaRecorder` chunked upload (worse latency, works) | Slightly slower turns |
| Media worker crashes | Session state intact (M6 checkpoints); reconnect re-establishes audio | Brief "reconnecting" |
| Everything audio fails | Text mode, session continues | "Audio's not working — let's continue by typing" |

---

## 11. Performance & cost budget

**Latency ledger (p95 targets, measured per turn):**

| Stage | Target |
|---|---|
| VAD decision after speech end | 400 ms |
| ASR final after VAD | 120 ms |
| LLM first token (with prefill) | 350 ms |
| TTS first audio | 250 ms |
| Network + jitter | 100 ms |
| **Total end-of-speech → first audio** | **1.2 s** |
| Barge-in stop | 350 ms |

**Cost per 45-min voice session:**
| Item | Cost |
|---|---|
| ASR (self-hosted) | compute only |
| TTS (~5,000 characters) | ₹9 |
| Speculative prefill waste (~30% cancel) | ₹0.7 |
| **Voice-specific total** | **≈ ₹10** |

---

## 12. Test plan

**Latency harness [the core test]** — an automated rig plays 50 recorded utterances of varying length and pace through the full pipeline and measures every stage. Runs nightly; regressions fail the build. **This is the single most valuable test in the module** — latency regresses silently otherwise.

**Endpointing** — 200 hand-labelled utterance endings (complete / incomplete); measure premature-cut rate (target < 3%) and over-wait rate (target < 10%).

**Barge-in** — automated: inject speech at 10 points during TTS; assert stop < 350 ms and correct `heard_up_to_ms` in all cases.

**ASR accent evaluation [GATE]** — WER on our pilot recordings, segmented by self-reported L1 group. Report per group. A > 8-point gap between groups blocks release.

**Network chaos** — simulate 5%/15%/30% packet loss, 200 ms/500 ms latency, and a 10-second blackout; assert graceful degradation at each level.

**Device matrix** — Chrome/Firefox/Safari on Windows, macOS, Android, iOS. Real devices, not emulators. iOS Safari will find bugs nothing else finds.

**Manual QA** (15 min): mic check → full voice turn → interrupt mid-question → confirm clean stop and truncated transcript → deliberately pause mid-sentence and confirm no cut-off → flag a mishearing → force push-to-talk → complete a turn.

---

## 13. Metrics & acceptance gates

| ID | Metric | Target |
|---|---|---|
| AC-11.1 **[GATE]** | p95 end-of-speech → first audio | ≤ 1.2 s |
| AC-11.2 **[GATE]** | Barge-in stop | ≤ 350 ms |
| AC-11.3 **[GATE]** | Premature cut-off rate | < 3% |
| AC-11.4 **[GATE]** | ASR WER gap between accent groups | ≤ 8 points |
| AC-11.5 | Overall WER on pilot audio | ≤ 12% |
| AC-11.6 | "It kept cutting me off" complaints | < 5% of sessions |
| AC-11.7 | Prefill cancel rate | 25–40% (outside → tune the window) |
| AC-11.8 | Voice session completion rate vs text | within 10 points |
| AC-11.9 | Push-to-talk fallback engages before abandonment | ≥ 80% of poor-network sessions |

---

## 14. Build order

> **Superseded by Revision 2 (§0).** The order now starts from what M06 ships;
> it is in the TODO's §7. Kept below as Revision 1's.

| Day | Task |
|---|---|
| 1 | WebRTC transport, media worker, audio in/out round trip |
| 2 | Silero VAD + basic endpointing + latency instrumentation from day one |
| 3 | Streaming `faster-whisper` + WhisperX alignment |
| 4 | Streaming TTS + clause chunking + persona voices |
| 5 | End-to-end turn; measure the baseline latency honestly |
| 6 | Barge-in: cancel chain + `heard_up_to_ms` + transcript truncation |
| 7 | Adaptive endpointing threshold |
| 8 | Semantic completeness classifier (label 2,000 endings, train, integrate) |
| 9 | Speculative prefill + cancel logic + cost tracking |
| 10 | Mic check with real transcription + noise floor calibration |
| 11 | Calibrated silence, backchannels, note-taking pauses |
| 12 | Captions, repeat, misheard flag, modality switch |
| 13 | Degradation ladder + push-to-talk |
| 14 | Latency harness, accent WER evaluation, device matrix |

---

## 15. Open decisions

1. **Managed TTS vs self-hosted from the start?** Managed is dramatically better for latency and prosody; self-hosted is free. Recommendation: **managed primary, Piper fallback**, revisit if TTS cost exceeds 15% of session cost.
   **Resolved 2026-10-05 (§0):** browser voices first (free, and the only Indian-English neural voices available), Kokoro in the browser as an opt-in second tier, managed streaming behind a flag. Piper is out: it moved to `piper1-gpl` (GPL-3.0).
2. **Do we contest barge-in in Final Boss?** It's realistic and uncomfortable. Proposal: ship it behind a flag, test with 10 students, keep only if the "felt realistic" score doesn't drop.
3. **Vernacular interviewing (full Hindi/Tamil rounds)** — out of Year-1 scope, but code-switch tolerance ships. Confirm with the placement cell whether a fully vernacular HR round would be used.
4. **Store full session audio by default?** Needed for M12 re-processing and evidence. Proposal: **yes for 180 days with explicit consent**, opt-out available, and the report explains what audio enables.
5. **Diarisation always-on cost** — pyannote on every session is real compute. Proposal: on for proctored mode always, on for practice only when a second-speaker heuristic fires.
6. **A face for the interviewer?** M06's open question 1 recommended "a simple animated presence indicator, not a face" — an uncanny 3D face is worse than none, and a real photo raises whose face it is — with "revisit if a student panel disagrees". The user asked on 2026-10-04 for realistic faces and voices. Options found on 2026-10-04, all free:
   - **A. The drawn face, talking** — shipping in M06 since 2026-10-05: a ring while speaking, the mouth opening on each word. The spec's recommendation.
   - **B. A realistic 3D head from one photo, in the browser.** LAM (Alibaba, Apache-2.0, SIGGRAPH 2025) builds it; `@myned-ai/gsplat-flame-avatar-renderer` (MIT) plays it in WebGL at 30 fps with 52 ARKit blendshapes and the eyes held on the student; `wav2arkit` (Apache-2.0, onnxruntime-web on the CPU) drives the lips from any audio. No server GPU; making each head needs a GPU once (LAM's online demo or a free notebook). `gsplat-talkinghead` (MIT) shows the whole chain.
   - **C. Stylised 3D** — TalkingHead (MIT) with HeadAudio; avatars from Avaturn, MPFB (CC0), VRoid or RocketBox (Ready Player Me shut down on 2026-01-31).
   - **D. Pre-rendered idle and speaking clips, crossfaded** (DeepInterview, Apache-2.0): real-looking at zero runtime cost; the lips only roughly match.
   - **E. Photoreal real-time lip-sync** (MuseTalk, LiveTalking, Ditto, LatentSync) needs an NVIDIA GPU server.
   Recommendation: keep A; put B beside A in front of a few students — the spec's own condition for changing its mind. Faces are AI-generated portraits, never a real person's, and labelled as AI.
   **Resolved 2026-10-08 — the user's decision: B, built** ("add faces to the interviews with perfect lip syncing"). A stays as what a tile shows until its head loads, and where WebGL is missing. Two departures from B as sketched: the lip-sync frames are made by M11 (`face.py`, wav2arkit on the server's CPU) and fetched by the key the sentence's audio came with, not computed in the browser; and the portraits and heads are made on this laptop (FLUX.1-schnell through stable-diffusion.cpp, then LAM on the CPU), not on a hosted demo. The browser side is Core's `TalkingHead` (v0.28.0). See the TODO's 2026-10-08 entry for what was measured.
