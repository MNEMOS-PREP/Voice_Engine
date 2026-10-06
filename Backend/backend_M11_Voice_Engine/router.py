"""M11's `/v1` surface (spec §7).

The identity guard is on the router, so it runs on every route below and on
every route added later (`access.py`).

Every path's first segment after `/v1` is `voice`: Platform_Shell proxies one
origin by that segment, and `voice` is this module's alone (the shell's
`vite.config.ts`, checked by `tests/test_scaffold.py`). `deps` is the one path
every module serves.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Literal

from ai_core.db import get_session
from ai_core.dependencies import DependencyStatus
from ai_core.guard import require_role
from ai_core.identity import Principal, Role
from ai_core.timeutil import utcnow
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import asr, ledger, tts
from .access import enforce_access
from .dependencies import deps
from .models import LineTiming

router = APIRouter(prefix="/v1", dependencies=[Depends(enforce_access)])

#: The ledger's summary is the team's view of the product, not a student's.
staff_only = require_role(Role.admin, Role.placement_officer, Role.researcher)


@router.get("/deps", response_model=list[DependencyStatus], tags=["meta"])
def dependencies(force: bool = False) -> list[DependencyStatus]:
    """Each upstream, whether it is up, and the sentence a student sees if not."""
    return deps().statuses(force=force)


# ─────────────────────────────────────────────────────────────────────────
#  The latency ledger (spec §5 TurnTiming, §11; TODO §7 day 2)
# ─────────────────────────────────────────────────────────────────────────

Mark = float | None
StopReason = Literal["barge_in", "mic", "send", "pause", "end", "repeat", "off", "leave"]


class LineTimingIn(BaseModel):
    """One spoken line, as `@ai/core`'s voice hook recorded it (`LineTiming`
    in `src/voice/ledger.ts` — keep the two in step)."""

    id: uuid.UUID
    key: str = Field(min_length=1, max_length=200)
    #: Which voice spoke it: the browser's own, or this module's (tts.py).
    tier: Literal["browser", "server"] = "browser"
    voice_name: str | None = Field(default=None, max_length=200)
    rate: float | None = Field(default=None, ge=0.1, le=10)
    line_chars: int = Field(ge=0, le=50_000)
    heard_chars: int | None = Field(default=None, ge=0, le=50_000)
    answer_sent_at: Mark = None
    first_token_at: Mark = None
    landed_at: float
    first_audio_at: Mark = None
    ended_at: Mark = None
    stop_requested_at: Mark = None
    stopped_at: Mark = None
    stop_reason: StopReason | None = None
    #: Barge-in (day 3): when the student began speaking over the line.
    speech_started_at: Mark = None
    #: Final Boss finished up to 1.5 s before yielding (§6.5), on purpose.
    contested: bool = False
    blocked: bool = False
    error: str | None = Field(default=None, max_length=100)


class LineTimingOut(LineTimingIn):
    session_id: uuid.UUID
    #: The spec's stages for this line, in ms; null where not measured.
    stages: dict[str, int | None]


class StageOut(BaseModel):
    name: str
    label: str
    n: int
    p50: int | None
    p95: int | None
    target_ms: int | None
    gate: str | None
    met: bool | None


class SummaryOut(BaseModel):
    days: int
    lines: int
    sessions: int
    stages: list[StageOut]
    blocked: int
    no_audio: int
    stops: dict[str, int]
    voices: dict[str, int]


def _out(row: LineTiming) -> LineTimingOut:
    return LineTimingOut(
        **row.model_dump(exclude={"candidate_id", "recorded_at"}),
        stages=ledger.stages_of(row),
    )


@router.post(
    "/voice/{session_id}/timings",
    response_model=LineTimingOut,
    tags=["ledger"],
)
def record_line(
    session_id: uuid.UUID,
    body: LineTimingIn,
    principal: Principal | None = Depends(enforce_access),
    db: Session = Depends(get_session),
) -> LineTimingOut:
    """Record one spoken line. Posting the same line id twice is one row."""
    if principal is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    existing = db.get(LineTiming, body.id)
    if existing is not None:
        if existing.session_id != session_id:
            raise HTTPException(status_code=409, detail="That line belongs to another interview.")
        return _out(existing)
    row = LineTiming(
        **body.model_dump(),
        session_id=session_id,
        candidate_id=principal.candidate_id if principal.role is Role.student else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get(
    "/voice/{session_id}/timings",
    response_model=list[LineTimingOut],
    tags=["ledger"],
)
def interview_timings(
    session_id: uuid.UUID, db: Session = Depends(get_session)
) -> list[LineTimingOut]:
    """Every line spoken in one interview, in the order it reached the room."""
    rows = db.exec(
        select(LineTiming).where(LineTiming.session_id == session_id).order_by(LineTiming.landed_at)
    ).all()
    return [_out(row) for row in rows]


@router.get(
    "/voice/timings/summary",
    response_model=SummaryOut,
    tags=["ledger"],
    dependencies=[Depends(staff_only)],
)
def timings_summary(
    days: int = Query(default=14, ge=1, le=365),
    db: Session = Depends(get_session),
) -> SummaryOut:
    """p50 and p95 of every stage across the cohort, against the spec's
    targets; how many lines never made a sound, and why lines were stopped."""
    since = utcnow() - timedelta(days=days)
    rows = db.exec(select(LineTiming).where(LineTiming.recorded_at >= since)).all()
    summary = ledger.summarise(rows)
    return SummaryOut(
        days=days,
        lines=summary.lines,
        sessions=summary.sessions,
        stages=[StageOut(**vars(stage)) for stage in summary.stages],
        blocked=summary.blocked,
        no_audio=summary.no_audio,
        stops=summary.stops,
        voices=summary.voices,
    )


# ─────────────────────────────────────────────────────────────────────────
#  The interviewer's voice, made here (tts.py; TODO §0, 2026-10-06)
# ─────────────────────────────────────────────────────────────────────────


class EngineOut(BaseModel):
    #: "off" (not installed or turned off) · "loading" · "ready" · "failed".
    state: Literal["off", "loading", "ready", "failed"]
    reason: str
    precision: str
    model: str


class VoiceOut(BaseModel):
    key: str
    label: str
    accent: str
    register: str
    pitch_hz: int
    source: str
    licence: str
    credit: str


class CastOut(BaseModel):
    default: str
    #: M06 persona id → voice key.
    cast: dict[str, str]
    voices: list[VoiceOut]


class SpeakIn(BaseModel):
    """One sentence to say. The browser splits a line into sentences
    (`splitSentences`), so the first is heard while the next is made."""

    text: str = Field(min_length=1, max_length=400)
    persona_id: str | None = Field(default=None, max_length=64)
    voice_id: str | None = Field(default=None, max_length=40)
    #: A voice by its key — the voice check plays a specific one.
    voice: str | None = Field(default=None, max_length=64)


@router.get("/voice/engine", response_model=EngineOut, tags=["voice"])
def voice_engine() -> EngineOut:
    """Whether the server voice can speak — a room asks once, and uses it for
    the whole interview or not at all, so the voice never changes mid-way."""
    e = tts.engine()
    e.start()  # idempotent: the first question wakes it if boot did not
    return EngineOut(state=e.state, reason=e.reason, precision=e.precision, model=tts.MODEL_ID)


@router.get("/voice/cast", response_model=CastOut, tags=["voice"])
def voice_cast() -> CastOut:
    """Who speaks for whom, and where each voice comes from."""
    cast = tts.engine().cast
    return CastOut(
        default=cast.default,
        cast=cast.cast,
        voices=[
            VoiceOut(**{k: getattr(v, k) for k in VoiceOut.model_fields})
            for v in cast.voices.values()
        ],
    )


@router.post(
    "/voice/speak",
    tags=["voice"],
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}, "description": "16-bit PCM WAV, 24 kHz"}},
)
def speak(body: SpeakIn, principal: Principal | None = Depends(enforce_access)) -> Response:
    """One sentence, in the voice cast for the interviewer. 503 when the server
    voice cannot speak — the browser's own voice says the line instead."""
    if principal is None:
        # Synthesis is the heaviest thing this module does; not for anybody.
        raise HTTPException(status_code=401, detail="Not signed in.")
    e = tts.engine()
    voice = e.cast.resolve(persona_id=body.persona_id, voice_id=body.voice_id, voice=body.voice)
    try:
        audio, cached, ms = e.speak(body.text, voice)
    except tts.EngineUnavailable as exc:
        raise HTTPException(
            status_code=503, detail=f"The interviewer's voice is not ready: {exc}"
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-Voice": voice.key,
            "X-Cache": "hit" if cached else "miss",
            "X-Synth-Ms": str(ms),
            "Cache-Control": "private, max-age=86400",
        },
    )


# ─────────────────────────────────────────────────────────────────────────
#  Hearing the student (spec §6.7, FR-11.3; TODO §7 day 4)
# ─────────────────────────────────────────────────────────────────────────


class AsrStateOut(BaseModel):
    available: bool
    model: str
    reason: str


@router.get("/voice/asr", response_model=AsrStateOut, tags=["voice"])
def asr_state() -> AsrStateOut:
    """Whether server recognition can run. When it cannot, the browser's own
    recognition takes the answer, as before day 4."""
    return AsrStateOut(**asr.state())


@router.post("/voice/transcribe", response_model=asr.ASRResult, tags=["voice"])
async def transcribe(
    request: Request,
    context: str | None = Query(default=None, max_length=600),
    principal: Principal | None = Depends(enforce_access),
) -> asr.ASRResult:
    """An answer's audio — the request body itself, `audio/wav` or
    `audio/webm` — and its words, each with its time (FR-11.3). `context` is
    the question being answered: it biases the recogniser toward the words
    the answer is likely to use. Nothing is kept: the audio is transcribed and
    dropped (keeping it is FR-11.19's, with consent). 503 when recognition
    cannot run — the browser's own recognition carries the answer instead."""
    if principal is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=415, detail="Send the audio itself, as audio/wav or audio/webm."
        )
    audio = await request.body()
    if len(audio) > asr.MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="That answer is too long to transcribe.")
    try:
        return await run_in_threadpool(asr.transcribe, audio, content_type, context=context)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except asr.AsrUnavailable as exc:
        raise HTTPException(
            status_code=503, detail=f"Speech recognition is not available: {exc}"
        ) from None


__all__ = ["router"]
