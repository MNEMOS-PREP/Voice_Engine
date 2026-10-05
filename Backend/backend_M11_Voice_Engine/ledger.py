"""The latency ledger — stages from marks, and the targets they answer to.

Spec §11's budget names the stages of one turn. Revision 2 has no media
worker, so the browser is where they are measured, and what it can see today
is narrower than the spec's list — said here rather than papered over:

    stage               from → to                         spec target (p95)
    ------------------  --------------------------------  -----------------
    total               answer sent → first audio         1,200 ms  AC-11.1
    first_token         answer sent → first token         350 ms (with prefill)
    line_ready          answer sent → line on screen      —
    tts_first_audio     line on screen → first audio      250 ms
    stop                stop asked → browser says stopped 350 ms    AC-11.2
    heard_up_to         first audio → stop asked          —  (FR-11.9's input)
    spoken              first audio → line finished       —

"Answer sent" stands in for the spec's end of speech while recognition is the
browser's: the student presses send. VAD (day 3) and server ASR (day 4) move
it to where speech actually ended, and `vad_decision` and `asr_final` join the
table then — not before, as columns nothing fills.

The targets live here and nowhere else. The browser records; this decides.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .models import LineTiming


@dataclass(frozen=True)
class Stage:
    name: str
    start: str
    end: str
    label: str
    #: p95 target in ms, or None for a stage measured but not budgeted.
    target_ms: int | None = None
    #: The acceptance gate this stage is, if any (spec §13).
    gate: str | None = None


STAGES: tuple[Stage, ...] = (
    Stage(
        "total", "answer_sent_at", "first_audio_at", "Answer sent → first audio", 1200, "AC-11.1"
    ),
    Stage("first_token", "answer_sent_at", "first_token_at", "Answer sent → first token", 350),
    Stage("line_ready", "answer_sent_at", "landed_at", "Answer sent → line on screen"),
    Stage("tts_first_audio", "landed_at", "first_audio_at", "Line on screen → first audio", 250),
    Stage("stop", "stop_requested_at", "stopped_at", "Stop asked → stopped", 350, "AC-11.2"),
    Stage("heard_up_to", "first_audio_at", "stop_requested_at", "Heard before the stop"),
    Stage("spoken", "first_audio_at", "ended_at", "Line spoken in full"),
)

BY_NAME = {stage.name: stage for stage in STAGES}


def stages_of(row: LineTiming) -> dict[str, int | None]:
    """Each stage's duration for one line, in whole ms; None when either mark
    is missing — or when the end precedes the start, which is a bad record, not
    a fast one."""
    out: dict[str, int | None] = {}
    for stage in STAGES:
        start, end = getattr(row, stage.start), getattr(row, stage.end)
        if start is None or end is None or end < start:
            out[stage.name] = None
        else:
            out[stage.name] = round(end - start)
    # A stop before any audio is not a heard-up-to of zero; nothing played.
    if row.first_audio_at is None:
        out["heard_up_to"] = None
    return out


def percentile(values: Sequence[float], p: float) -> int | None:
    """Nearest-rank percentile: a value that actually occurred, never an
    interpolation between two lines that did not happen."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return round(ordered[rank - 1])


@dataclass(frozen=True)
class StageSummary:
    name: str
    label: str
    n: int
    p50: int | None
    p95: int | None
    target_ms: int | None
    gate: str | None
    #: p95 within target; None when there is no target or nothing measured.
    met: bool | None


@dataclass(frozen=True)
class Summary:
    lines: int
    sessions: int
    stages: list[StageSummary]
    #: Lines whose audio never began, and why, as far as the browser said.
    blocked: int
    no_audio: int
    stops: dict[str, int]
    voices: dict[str, int]


def summarise(rows: Iterable[LineTiming]) -> Summary:
    rows = list(rows)
    per_stage: dict[str, list[int]] = {stage.name: [] for stage in STAGES}
    for row in rows:
        for name, value in stages_of(row).items():
            if value is not None:
                per_stage[name].append(value)
    stages = []
    for stage in STAGES:
        values = per_stage[stage.name]
        p95 = percentile(values, 95)
        met = None if stage.target_ms is None or p95 is None else p95 <= stage.target_ms
        stages.append(
            StageSummary(
                name=stage.name,
                label=stage.label,
                n=len(values),
                p50=percentile(values, 50),
                p95=p95,
                target_ms=stage.target_ms,
                gate=stage.gate,
                met=met,
            )
        )
    unheard = [
        r
        for r in rows
        if r.first_audio_at is None and r.stop_requested_at is None and not r.blocked
    ]
    return Summary(
        lines=len(rows),
        sessions=len({r.session_id for r in rows}),
        stages=stages,
        blocked=sum(1 for r in rows if r.blocked),
        no_audio=len(unheard),
        stops=dict(Counter(r.stop_reason for r in rows if r.stop_reason)),
        voices=dict(Counter(r.voice_name or "browser default" for r in rows)),
    )


__all__ = ["BY_NAME", "STAGES", "Stage", "Summary", "percentile", "stages_of", "summarise"]
