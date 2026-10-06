"""Tables — spec §5.

`m11_line_timing` is the latency ledger (§5 `TurnTiming`, §11): one row per
line the interviewer spoke, as the browser measured it. It stores the MARKS
the browser saw — when a line landed, when its audio began, when it ended or
was stopped — not the stage durations: those are derived on read
(`ledger.py`), so a change to how a stage is defined re-reads every row
instead of leaving old rows meaning something else.

The row's id is made by the browser, so a post that is retried after a
dropped response is the same row, not a second one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from ai_core.timeutil import utcnow
from sqlmodel import Field, SQLModel


class LineTiming(SQLModel, table=True):
    __tablename__ = "m11_line_timing"

    id: uuid.UUID = Field(primary_key=True)
    #: M06's interview id: the session the line was said in.
    session_id: uuid.UUID = Field(index=True)
    #: Whose interview, from the principal that posted the first line of it.
    candidate_id: str | None = Field(default=None, index=True)
    #: The room's name for the line: a turn id, "idle", "repeat".
    key: str
    tier: str = "browser"
    voice_name: str | None = None
    rate: float | None = None
    line_chars: int = 0
    heard_chars: int | None = None
    # Epoch milliseconds on the page's monotonic clock. Only differences
    # between marks of one line are read, so client clock skew cancels out.
    answer_sent_at: float | None = None
    first_token_at: float | None = None
    #: Day 5: where a spoken answer's speech ended — AC-11.1's start.
    speech_ended_at: float | None = None
    landed_at: float
    first_audio_at: float | None = None
    ended_at: float | None = None
    stop_requested_at: float | None = None
    stopped_at: float | None = None
    stop_reason: str | None = Field(default=None, index=True)
    #: Barge-in (day 3): when the student began speaking over the line — its
    #: first loud frame, before the 250 ms that made it count (§6.5).
    speech_started_at: float | None = None
    #: The interviewer finished up to 1.5 s before yielding, on purpose
    #: (Final Boss, §6.5): not a slow stop.
    contested: bool = False
    blocked: bool = False
    error: str | None = None
    recorded_at: datetime = Field(default_factory=utcnow, index=True)


class LexiconFlag(SQLModel, table=True):
    """Someone heard a word said wrong (EC-11.11, "crowd-flaggable")."""

    __tablename__ = "m11_lexicon_flag"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    #: The word as written — what the line said.
    word: str = Field(index=True, max_length=60)
    #: The voice that said it wrong, when known.
    voice: str | None = Field(default=None, max_length=64)
    #: How it sounded, in the flagger's words, if they said.
    heard_as: str | None = Field(default=None, max_length=60)
    candidate_id: str | None = Field(default=None, index=True)
    flagged_at: datetime = Field(default_factory=utcnow, index=True)


__all__ = ["LexiconFlag", "LineTiming"]
