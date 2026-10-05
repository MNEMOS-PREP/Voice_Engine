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
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import ledger
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
    tier: Literal["browser"] = "browser"
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


__all__ = ["router"]
