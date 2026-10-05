# M11 — Voice & Conversation Engine

> **Everything about realism lives or dies here. This is a latency-engineering module.**
>
> Spec: [plan_in_depth/M11_Voice_Engine.md](plan_in_depth/M11_Voice_Engine.md) (Revision 2: browser-first and free) · Running state: [the TODO](plan_in_depth/M11_Voice_Engine_TODO.md) · Ports: API `8111`, web `5211`, WebSocket `8211` reserved ([PORTS.txt](PORTS.txt))

Interviews are spoken, and spoken interaction is a timing problem before it is an AI problem. This module owns the loop: hearing the student, deciding when they have finished, speaking the interviewer's line in a persona's voice, and stopping within 350 ms when the student starts talking.

```bash
git clone https://github.com/MNEMOS-PREP/Voice_Engine
cd Voice_Engine/Backend
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest          # no network, no API key
cd ../Frontend && npm install && cd ..
start_voice.bat                         # API on :8111, the voice check on :5211
```

Nothing upstream is needed to boot, test or run. [`/v1/deps`](dependencies.txt) says whether M06 is up.

---

## Where the code is

**Two halves, in two places, on purpose.**

| Half | Where | Why there |
|---|---|---|
| The interviewer's voice in the browser: choosing a voice for a persona's `voice_id`, speaking a line a sentence at a time, stopping, the mouth for the face | [`@ai/core`](https://github.com/MNEMOS-PREP/Platform_Core) `src/voice/` (since v0.14.0) | More than one module speaks — M06's interview room and this module's voice check now, M14's discussion room next. A copy per module drifts; one module frontend importing another's stops it running alone. It is M11's code; changes to it are made here in M11's plan and released through core. |
| What outlives a page or a browser cannot do: the latency ledger, stored audio, server ASR with word timestamps | `Backend/backend_M11_Voice_Engine` | This repo |
| M11's own screens | `Frontend/frontend_M11_Voice_Engine` — `/voice` | This repo, mounted whole by Platform_Shell |

## Where it stands

**Days 1–2 of the [Revision 2 build order](plan_in_depth/M11_Voice_Engine_TODO.md#revision-2-build-order-2026-10-05)**: the frame, and the latency ledger. The module boots alone, its one upstream (M06) is optional with a sentence a student can act on, the identity guard is on the router, the first screen plays every interviewer in the voice this browser gives them, and every line an interviewer speaks is now measured.

| Landed | |
|---|---|
| **The voice client in core** | `useInterviewerVoice` and its pure functions moved from M06 to `@ai/core` v0.14.0 with their tests. M06 imports it from there. |
| **The voice check** (`/voice`) | M06's interviewers, read from M06's persona files through `/v1/interviews/personas`, each with the browser voice chosen for them and a play button; says when several share a voice (FR-11.21), and when M06 is down plays one sample voice with M06's own sentence. |
| **Identity before endpoints** | [`access.py`](Backend/backend_M11_Voice_Engine/access.py): `ai_core.guard` on the router. Platform_Core's stranger check runs from the first commit. |
| **Its noun is its own** | `/v1/voice`, held against Platform_Shell's live proxy table by a test that reads the shell's `vite.config.ts`. |
| **The latency ledger** (spec §5 `TurnTiming`, §11) | The browser records each spoken line's marks (`@ai/core` v0.15.0); `POST/GET /v1/voice/{session_id}/timings` keeps them, one row per line, idempotent on the browser's line id, readable only by the student whose interview it is and by staff. [`ledger.py`](Backend/backend_M11_Voice_Engine/ledger.py) turns marks into the spec's stages and holds the targets in one place; staff see p50 / p95 per stage against budget on `/voice`. |

**First numbers, measured live** (headless Edge, the Neerja online voice, real model): answer sent → first audio **1.1–1.4 s** (AC-11.1: 1.2 s at p95 — over); the model's first token 0.7–1.0 s; the voice ~0.3 s after a line lands, but **2–3 s for a page's first line** (the online voice's cold start); a stop **6–9 ms**.

Next: browser VAD barge-in (day 3).

## Layout

```
Backend/
  backend_M11_Voice_Engine/
    app.py            FastAPI app, /health, /status
    router.py         /v1 routes (spec §7)
    access.py         identity, router-level; an interview id resolved to its student
    models.py         m11_line_timing — the latency ledger, marks not durations
    ledger.py         marks → the spec's stages; the targets, in one place
    dependencies.py   upstream probing from module.json
    tests/            no test opens a socket
Frontend/
  frontend_M11_Voice_Engine/
    src/routes.tsx    /voice — mounted by Platform_Shell
    src/components/   VoiceCheck, LatencyLedger (staff)
scripts/              launcher (launch.ps1, pane.ps1, control.ps1, services.txt)
plan_in_depth/        the spec and the TODO
```
