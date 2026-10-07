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

from . import asr, kept, ledger, lexicon, tts, turn
from .access import enforce_access
from .dependencies import deps
from .models import KeptAnswer, LexiconFlag, LineTiming

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
    #: Day 5: where a spoken answer's speech ended (AC-11.1's start).
    speech_ended_at: Mark = None
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
    session_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_session),
) -> SummaryOut:
    """p50 and p95 of every stage across the cohort, against the spec's
    targets; how many lines never made a sound, and why lines were stopped.
    With `session_id`, one interview's — what the latency harness grades
    (`scripts/latency_harness.mjs`), against the same targets."""
    since = utcnow() - timedelta(days=days)
    query = select(LineTiming).where(LineTiming.recorded_at >= since)
    if session_id is not None:
        query = query.where(LineTiming.session_id == session_id)
    rows = db.exec(query).all()
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
    #: The browser's id for the line this sentence is part of (`plan`).
    line: str | None = Field(default=None, max_length=64)


class PlanIn(BaseModel):
    """A whole line's sentences, the moment the line arrives: M11 starts
    making them side by side, three at a time, and `speak` collects each."""

    line: str = Field(min_length=1, max_length=64)
    sentences: list[SpeakIn] = Field(min_length=1, max_length=24)


class DropIn(BaseModel):
    """Lines the browser stopped (a barge-in, a repeat)."""

    lines: list[str] = Field(min_length=1, max_length=32)


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
        audio, cached, ms = e.speak(body.text, voice, line=body.line)
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


@router.post("/voice/plan", status_code=202, tags=["voice"])
def plan_line(
    body: PlanIn, principal: Principal | None = Depends(enforce_access)
) -> dict[str, int]:
    """Start making a line's sentences now, side by side (2026-10-07). The
    browser still asks for each in order (`/voice/speak`); by then most are
    made. Nothing to wait for here: 202 at once."""
    if principal is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    e = tts.engine()
    sentences = [
        (s.text, e.cast.resolve(persona_id=s.persona_id, voice_id=s.voice_id, voice=s.voice))
        for s in body.sentences
    ]
    return {"planned": e.plan(sentences, body.line)}


@router.post("/voice/drop", tags=["voice"])
def drop_lines(
    body: DropIn, principal: Principal | None = Depends(enforce_access)
) -> dict[str, int]:
    """The browser stopped these lines: what is not yet started is not made."""
    if principal is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return {"dropped": tts.engine().drop(body.lines)}


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


# ─────────────────────────────────────────────────────────────────────────
#  Has the student finished? (spec §6.3, FR-11.5; TODO §7 day 5)
# ─────────────────────────────────────────────────────────────────────────


class TurnStateOut(BaseModel):
    state: Literal["off", "loading", "ready", "failed"]
    reason: str
    model: str


class TurnOut(BaseModel):
    #: Smart Turn's probability that the speech before the silence is a
    #: finished turn; `finished` is it over 0.5.
    probability: float
    finished: bool
    latency_ms: int


@router.get("/voice/turn", response_model=TurnStateOut, tags=["voice"])
def turn_state() -> TurnStateOut:
    """Whether the turn model is ready. When it is not, the browser ends a
    turn on silence alone (the adaptive threshold, FR-11.4)."""
    c = turn.classifier()
    return TurnStateOut(state=c.state, reason=c.reason, model=turn.FILE)


@router.post("/voice/turn", response_model=TurnOut, tags=["voice"])
async def turn_finished(
    request: Request, principal: Principal | None = Depends(enforce_access)
) -> TurnOut:
    """The last seconds of the student's speech up to a silence — 16 kHz
    16-bit mono WAV, the body itself — and whether it sounds finished. Nothing
    is kept. 503 when the model cannot answer."""
    if principal is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in ("audio/wav", "audio/x-wav", "audio/wave"):
        raise HTTPException(status_code=415, detail="Send 16 kHz 16-bit mono WAV.")
    data = await request.body()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Send the last few seconds, not the answer.")
    try:
        audio = turn.read_wav(data)
        probability, ms = await run_in_threadpool(turn.classifier().finished, audio)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except turn.TurnUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"The turn model is not ready: {exc}") from None
    return TurnOut(
        probability=round(probability, 4), finished=probability > turn.THRESHOLD, latency_ms=ms
    )


# ─────────────────────────────────────────────────────────────────────────
#  Words the voices get wrong (EC-11.11)
# ─────────────────────────────────────────────────────────────────────────


class LexiconEntryOut(BaseModel):
    term: str
    say: str
    exact: bool = False
    why: str | None = None
    #: The voices this respelling is for; empty means every voice.
    voices: list[str] = Field(default_factory=list)


class FlagIn(BaseModel):
    word: str = Field(min_length=1, max_length=60)
    voice: str | None = Field(default=None, max_length=64)
    heard_as: str | None = Field(default=None, max_length=60)


class FlagCount(BaseModel):
    word: str
    flags: int
    #: Already respelled in the table.
    fixed: bool
    heard_as: list[str]


@router.get("/voice/lexicon", response_model=list[LexiconEntryOut], tags=["voice"])
def lexicon_table() -> list[LexiconEntryOut]:
    """How the voices say the words they got wrong, and why each is here."""
    keep = ("term", "say", "exact", "why", "voices")
    return [LexiconEntryOut(**{k: e[k] for k in keep if k in e}) for e in lexicon.entries()]


@router.post("/voice/lexicon/flags", status_code=201, tags=["voice"])
def flag_word(
    body: FlagIn,
    principal: Principal | None = Depends(enforce_access),
    db: Session = Depends(get_session),
) -> dict[str, str]:
    """A word said wrong. Staff see it; the probe checks it."""
    if principal is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    db.add(
        LexiconFlag(
            word=" ".join(body.word.split()),
            voice=body.voice,
            heard_as=body.heard_as,
            candidate_id=principal.candidate_id if principal.role is Role.student else None,
        )
    )
    db.commit()
    return {"status": "flagged"}


@router.get(
    "/voice/lexicon/flags",
    response_model=list[FlagCount],
    dependencies=[Depends(staff_only)],
    tags=["voice"],
)
def lexicon_flags(db: Session = Depends(get_session)) -> list[FlagCount]:
    """Every flagged word, most-flagged first, and whether it is fixed."""
    fixed = {e["term"].lower() for e in lexicon.entries()}
    by_word: dict[str, list[LexiconFlag]] = {}
    for row in db.exec(select(LexiconFlag)).all():
        by_word.setdefault(row.word.lower(), []).append(row)
    out = [
        FlagCount(
            word=rows[0].word,
            flags=len(rows),
            fixed=word in fixed,
            heard_as=sorted({r.heard_as for r in rows if r.heard_as}),
        )
        for word, rows in by_word.items()
    ]
    return sorted(out, key=lambda f: (-f.flags, f.word))


# ─────────────────────────────────────────────────────────────────────────
#  Spoken answers, kept with consent (FR-11.19; TODO §7 day 12)
# ─────────────────────────────────────────────────────────────────────────


class KeptAnswerOut(BaseModel):
    turn_id: uuid.UUID
    duration_ms: int
    started_at: float | None
    ended_at: float | None


@router.post(
    "/voice/{session_id}/audio", response_model=KeptAnswerOut, status_code=201, tags=["voice"]
)
async def keep_answer(
    session_id: uuid.UUID,
    request: Request,
    turn_id: uuid.UUID = Query(),
    consent: str = Query(default="no"),
    started_at: float | None = Query(default=None),
    ended_at: float | None = Query(default=None),
    principal: Principal | None = Depends(enforce_access),
    db: Session = Depends(get_session),
) -> KeptAnswerOut:
    """One spoken answer's audio (16 kHz WAV, the body itself), kept beside
    the turn it answered. Only with the student's say-so — `consent=yes` —
    or nothing is written."""
    if principal is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    if consent != "yes":
        raise HTTPException(
            status_code=403, detail="Answers are kept only when the student chooses to keep them."
        )
    data = await request.body()
    if len(data) > kept.MAX_BYTES:
        raise HTTPException(status_code=413, detail="That answer is too long to keep.")
    try:
        duration = kept.duration_ms(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    kept.save(session_id, turn_id, data)
    row = db.exec(
        select(KeptAnswer).where(KeptAnswer.session_id == session_id, KeptAnswer.turn_id == turn_id)
    ).first() or KeptAnswer(session_id=session_id, turn_id=turn_id)
    row.duration_ms = duration
    row.started_at = started_at
    row.ended_at = ended_at
    row.candidate_id = principal.candidate_id if principal.role is Role.student else None
    db.add(row)
    db.commit()
    return KeptAnswerOut(
        turn_id=turn_id, duration_ms=duration, started_at=started_at, ended_at=ended_at
    )


@router.get("/voice/{session_id}/audio", response_model=list[KeptAnswerOut], tags=["voice"])
def kept_answers(session_id: uuid.UUID, db: Session = Depends(get_session)) -> list[KeptAnswerOut]:
    """The interview's kept answers, in the order they were said."""
    rows = db.exec(
        select(KeptAnswer).where(KeptAnswer.session_id == session_id).order_by(KeptAnswer.kept_at)
    ).all()
    return [
        KeptAnswerOut(
            turn_id=r.turn_id,
            duration_ms=r.duration_ms,
            started_at=r.started_at,
            ended_at=r.ended_at,
        )
        for r in rows
        if kept.path_for(session_id, r.turn_id).exists()
    ]


@router.get("/voice/{session_id}/audio/{turn_id}", tags=["voice"])
def kept_answer_audio(session_id: uuid.UUID, turn_id: uuid.UUID) -> Response:
    """One kept answer, to play back beside its words."""
    path = kept.path_for(session_id, turn_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="That answer was not kept.")
    return Response(
        content=path.read_bytes(),
        media_type="audio/wav",
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/voice/{session_id}/audio", status_code=204, tags=["voice"])
def forget_kept_answers(session_id: uuid.UUID, db: Session = Depends(get_session)) -> Response:
    """Delete every kept answer of this interview — the files, not just
    the rows."""
    for row in db.exec(select(KeptAnswer).where(KeptAnswer.session_id == session_id)).all():
        db.delete(row)
    db.commit()
    kept.forget(session_id)
    return Response(status_code=204)


__all__ = ["router"]
