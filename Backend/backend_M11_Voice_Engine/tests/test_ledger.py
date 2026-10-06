"""The latency ledger — spec §5 `TurnTiming`, §11, §13 (TODO §7, day 2).

What is pinned: the stages are read from the browser's marks the way the
spec's budget names them; a percentile is a value that happened; the targets
decide met / not met in one place; and the ledger is a student's own — a
stranger can neither read an interview's lines nor post into it, and the
cohort summary is staff's.
"""

from __future__ import annotations

import uuid

import pytest
from ai_core.testing import OWNER, STRANGER, assert_refuses_strangers, assert_staff_only
from sqlmodel import Session

from backend_M11_Voice_Engine import ledger
from backend_M11_Voice_Engine.app import app
from backend_M11_Voice_Engine.models import LineTiming

from .conftest import admin, student

T0 = 1_759_000_000_000.0  # an epoch-ms instant; only differences are read


def line(**marks) -> dict:
    """A line as `@ai/core`'s hook posts it: answered, spoken, finished."""
    body = {
        "id": str(uuid.uuid4()),
        "key": "turn-1",
        "tier": "browser",
        "voice_name": "Microsoft Neerja Online (Natural) - English (India)",
        "rate": 0.97,
        "line_chars": 120,
        "heard_chars": 120,
        "answer_sent_at": T0,
        "first_token_at": T0 + 300,
        "speech_ended_at": None,
        "landed_at": T0 + 900,
        "first_audio_at": T0 + 1100,
        "ended_at": T0 + 6100,
        "stop_requested_at": None,
        "stopped_at": None,
        "stop_reason": None,
        "speech_started_at": None,
        "contested": False,
        "blocked": False,
        "error": None,
    }
    body.update(marks)
    return body


def row(**marks) -> LineTiming:
    body = line(**marks)
    body["id"] = uuid.UUID(body["id"])
    return LineTiming(session_id=uuid.uuid4(), **body)


# ── stages, from marks ───────────────────────────────────────────────────


def test_stages_are_the_differences_the_spec_budget_names():
    stages = ledger.stages_of(row())
    assert stages["total"] == 1100  # answer sent → first audio (a typed turn's end)
    assert stages["first_token"] == 300
    assert stages["line_ready"] == 900
    assert stages["tts_first_audio"] == 200  # line on screen → first audio
    assert stages["spoken"] == 5000
    assert stages["stop"] is None and stages["heard_up_to"] is None


def test_a_line_cut_short_says_how_long_the_stop_took_and_how_much_was_heard():
    stages = ledger.stages_of(
        row(ended_at=None, stop_requested_at=T0 + 2600, stopped_at=T0 + 2640, stop_reason="mic")
    )
    assert stages["stop"] == 40  # AC-11.2 measures this
    assert stages["heard_up_to"] == 1500  # first audio → stop asked
    assert stages["spoken"] is None


def test_a_spoken_answer_is_timed_from_the_end_of_its_speech():
    """Day 5, AC-11.1 as the spec states it: speech ended at -900 ms (the
    turn was judged finished and written down meanwhile), first audio at
    +1,100 — two seconds, of which 900 ms were the wait for "finished"."""
    stages = ledger.stages_of(row(speech_ended_at=T0 - 900))
    assert stages["end_to_audio"] == 2000
    assert stages["endpoint"] == 900
    assert stages["total"] == 1100
    typed = ledger.stages_of(row())
    assert typed["end_to_audio"] is None and typed["endpoint"] is None


def test_a_barge_in_is_timed_from_the_students_first_word():
    """Day 3: the student began at +2,300 ms; 250 ms later it counted as
    speech and the stop was asked; the interviewer was quiet 40 ms after."""
    stages = ledger.stages_of(
        row(
            ended_at=None,
            speech_started_at=T0 + 2300,
            stop_requested_at=T0 + 2560,
            stopped_at=T0 + 2600,
            stop_reason="barge_in",
        )
    )
    assert stages["barge_in"] == 300
    assert stages["stop"] == 40
    assert stages["heard_up_to"] == 1460
    assert stages["contested"] is None


def test_a_final_boss_contest_is_not_a_slow_barge_in():
    """§6.5: Final Boss finishes up to 1.5 s before yielding, on purpose.
    Found on the first live one: 1,763 ms read against a 600 ms budget."""
    stages = ledger.stages_of(
        row(
            ended_at=None,
            speech_started_at=T0 + 2300,
            stop_requested_at=T0 + 4060,
            stopped_at=T0 + 4061,
            stop_reason="barge_in",
            contested=True,
        )
    )
    assert stages["barge_in"] is None
    assert stages["contested"] == 1761
    assert stages["stop"] == 1


def test_a_line_stopped_before_any_audio_heard_nothing_rather_than_zero():
    stages = ledger.stages_of(
        row(first_audio_at=None, ended_at=None, stop_requested_at=T0 + 950, stopped_at=T0 + 950)
    )
    assert stages["heard_up_to"] is None and stages["total"] is None
    assert stages["stop"] == 0


def test_a_line_with_no_answer_before_it_has_no_total():
    """The opening question, a repeat, an idle prompt: nothing was answered."""
    stages = ledger.stages_of(row(answer_sent_at=None, first_token_at=None))
    assert stages["total"] is None and stages["first_token"] is None
    assert stages["tts_first_audio"] == 200


def test_marks_out_of_order_are_a_bad_record_not_a_fast_line():
    stages = ledger.stages_of(row(first_audio_at=T0 + 800))  # before it landed
    assert stages["tts_first_audio"] is None


def test_a_percentile_is_a_value_that_happened():
    assert ledger.percentile([], 95) is None
    assert ledger.percentile([300], 95) == 300
    values = list(range(1, 101))  # 1..100
    assert ledger.percentile(values, 50) == 50
    assert ledger.percentile(values, 95) == 95
    assert ledger.percentile([100, 900], 95) == 900


def test_the_summary_holds_each_stage_to_its_target():
    rows = [row(first_audio_at=T0 + 1100 + i * 10, ended_at=T0 + 9000) for i in range(20)]
    by_name = {s.name: s for s in ledger.summarise(rows).stages}
    total = by_name["total"]
    assert total.n == 20 and total.target_ms == 1200 and total.gate is None
    assert total.p95 == 1280 and total.met is False
    # AC-11.1 is measured from where speech ended — typed lines have none.
    assert by_name["end_to_audio"].gate == "AC-11.1" and by_name["end_to_audio"].n == 0
    tts = by_name["tts_first_audio"]
    assert (tts.p50, tts.p95, tts.met) == (290, 380, False)  # 250 ms is the budget
    assert by_name["line_ready"].met is None  # measured, not budgeted
    assert by_name["stop"].n == 0 and by_name["stop"].met is None


def test_the_summary_counts_lines_that_made_no_sound_and_why_lines_stopped():
    rows = [
        row(),
        row(first_audio_at=None, ended_at=None, blocked=True),
        row(first_audio_at=None, ended_at=None),
        row(ended_at=None, stop_requested_at=T0 + 2000, stopped_at=T0 + 2010, stop_reason="mic"),
        row(ended_at=None, stop_requested_at=T0 + 2000, stopped_at=T0 + 2010, stop_reason="mic"),
        row(ended_at=None, stop_requested_at=T0 + 2000, stopped_at=T0 + 2030, stop_reason="send"),
    ]
    summary = ledger.summarise(rows)
    assert summary.lines == 6
    assert summary.blocked == 1 and summary.no_audio == 1
    assert summary.stops == {"mic": 2, "send": 1}


# ── the routes ───────────────────────────────────────────────────────────


@pytest.fixture
def interview() -> str:
    return str(uuid.uuid4())


def test_a_student_records_a_line_and_reads_it_back_with_its_stages(client, interview):
    me = uuid.uuid4()
    posted = client.post(f"/v1/voice/{interview}/timings", json=line(), headers=student(me))
    assert posted.status_code == 200, posted.text
    assert posted.json()["stages"]["total"] == 1100
    got = client.get(f"/v1/voice/{interview}/timings", headers=student(me)).json()
    assert [r["id"] for r in got] == [posted.json()["id"]]
    assert "candidate_id" not in got[0]


def test_the_same_line_posted_twice_is_one_row(client, interview):
    """The browser retries a dropped response; the ledger must not count it twice."""
    me = student(uuid.uuid4())
    body = line()
    client.post(f"/v1/voice/{interview}/timings", json=body, headers=me)
    again = client.post(f"/v1/voice/{interview}/timings", json=body, headers=me)
    assert again.status_code == 200
    assert len(client.get(f"/v1/voice/{interview}/timings", headers=me).json()) == 1


def test_a_line_id_cannot_be_moved_to_another_interview(client, interview):
    me = student(uuid.uuid4())
    body = line()
    client.post(f"/v1/voice/{interview}/timings", json=body, headers=me)
    moved = client.post(f"/v1/voice/{uuid.uuid4()}/timings", json=body, headers=me)
    assert moved.status_code == 409


def test_nobody_signed_in_cannot_start_a_ledger(client, interview):
    assert client.post(f"/v1/voice/{interview}/timings", json=line()).status_code == 401


def test_a_stranger_can_neither_read_nor_write_someone_elses_interview(client, engine):
    """Platform_Core's own check, pointed at the interview id: an interview
    owned by OWNER, asked about as nobody and as another student."""
    with Session(engine) as db:
        db.add(
            LineTiming(
                session_id=uuid.UUID(OWNER), candidate_id=OWNER, **{**line(), "id": uuid.uuid4()}
            )
        )
        db.commit()
    checked = assert_refuses_strangers(client, app, params=("session_id",), expect_at_least=2)
    assert ("POST", "/v1/voice/{session_id}/timings") in checked
    assert ("GET", "/v1/voice/{session_id}/timings") in checked
    # And the owner still gets in.
    assert client.get(f"/v1/voice/{OWNER}/timings", headers=student(OWNER)).status_code == 200
    assert client.get(f"/v1/voice/{OWNER}/timings", headers=student(STRANGER)).status_code == 403


def test_staff_read_any_interview(client, interview):
    client.post(f"/v1/voice/{interview}/timings", json=line(), headers=student(uuid.uuid4()))
    assert len(client.get(f"/v1/voice/{interview}/timings", headers=admin()).json()) == 1


@pytest.mark.gate
def test_the_cohort_summary_is_staff_only(client):
    """Platform_Core's check, from the route's own declared roles."""
    assert_staff_only(client, app)
    assert client.get("/v1/voice/timings/summary", headers=student(uuid.uuid4())).status_code == 403


def test_the_summary_reads_what_was_recorded(client):
    for i in range(3):
        session = str(uuid.uuid4())
        client.post(
            f"/v1/voice/{session}/timings",
            json=line(first_audio_at=T0 + 1000 + i * 100),
            headers=student(uuid.uuid4()),
        )
    body = client.get("/v1/voice/timings/summary", headers=admin()).json()
    assert body["lines"] == 3 and body["sessions"] == 3
    total = next(s for s in body["stages"] if s["name"] == "total")
    assert (total["p50"], total["p95"], total["met"]) == (1100, 1200, True)
    # One interview's, for the latency harness.
    one = client.get(f"/v1/voice/timings/summary?session_id={session}", headers=admin()).json()
    assert one["lines"] == 1 and one["sessions"] == 1
