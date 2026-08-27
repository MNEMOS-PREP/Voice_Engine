# M11 — TODO · Voice & Conversation Engine

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

## 0. Ideas and scouting

Things worth building that did not come from the spec — usually from reading
somebody else's implementation. **New ideas go at the top of this section.**

The rule we keep arriving at: borrow a **technique**, not a **component**. The
platform's contracts — character offsets, per-fact provenance, permanent
evidence — are more demanding than general-purpose tools assume, so integration
usually costs more than reimplementing the one idea we actually wanted.

_Nothing scouted for this module yet._

---

## 1. Where the module stands

| | |
|---|---|
| Status | **Not started.** No code exists — no backend, no frontend, no tests. |
| Spec | Written, and the source of every row below. |
| Scope | 22 functional requirements (18 of them P0), 9 acceptance metrics (4 release-blocking), 15 edge cases. |

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

