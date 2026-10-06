"""Spoken answers, kept with consent — FR-11.19 (TODO §7, day 12).

What is pinned: nothing is written without the student's say-so; a kept
answer is the student's — read back by them or staff, never a stranger;
it carries the clock it was said on; and deleting an interview's answers
removes the files, not just the rows.
"""

from __future__ import annotations

import io
import uuid
import wave

from backend_M11_Voice_Engine import kept

from .conftest import admin, student

OWNER = "0f3a2b1c-5d4e-4f6a-8b7c-9d0e1f2a3b4c"
STRANGER = "7e6d5c4b-3a29-4180-9f8e-7d6c5b4a3928"


def wav(seconds: float = 1.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def keep(client, session, turn, who=OWNER, consent="yes", body=None):
    return client.post(
        f"/v1/voice/{session}/audio?turn_id={turn}&consent={consent}&started_at=1000&ended_at=2500",
        content=body if body is not None else wav(),
        headers={**student(who), "Content-Type": "audio/wav"},
    )


def test_nothing_is_kept_without_consent(client):
    session, turn = uuid.uuid4(), uuid.uuid4()
    r = keep(client, session, turn, consent="no")
    assert r.status_code == 403
    assert not kept.path_for(session, turn).exists()
    assert client.post(f"/v1/voice/{session}/audio?turn_id={turn}&consent=yes").status_code == 401


def test_a_kept_answer_plays_back_to_its_student_on_its_clock(client):
    session, turn = uuid.uuid4(), uuid.uuid4()
    r = keep(client, session, turn)
    assert r.status_code == 201, r.text
    assert r.json() == {
        "turn_id": str(turn),
        "duration_ms": 1500,
        "started_at": 1000.0,
        "ended_at": 2500.0,
    }
    listed = client.get(f"/v1/voice/{session}/audio", headers=student(OWNER)).json()
    assert [a["turn_id"] for a in listed] == [str(turn)]
    audio = client.get(f"/v1/voice/{session}/audio/{turn}", headers=student(OWNER))
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert audio.content == wav()
    assert client.get(f"/v1/voice/{session}/audio/{turn}", headers=admin()).status_code == 200


def test_a_stranger_can_neither_hear_nor_add_to_someone_elses_answers(client):
    session, turn = uuid.uuid4(), uuid.uuid4()
    keep(client, session, turn)
    assert (
        client.get(f"/v1/voice/{session}/audio/{turn}", headers=student(STRANGER)).status_code
        == 403
    )
    assert client.get(f"/v1/voice/{session}/audio", headers=student(STRANGER)).status_code == 403
    assert keep(client, session, uuid.uuid4(), who=STRANGER).status_code == 403
    assert client.delete(f"/v1/voice/{session}/audio", headers=student(STRANGER)).status_code == 403


def test_deleting_removes_the_files_not_just_the_rows(client):
    session = uuid.uuid4()
    turns = [uuid.uuid4(), uuid.uuid4()]
    for turn in turns:
        keep(client, session, turn)
    assert all(kept.path_for(session, t).exists() for t in turns)
    assert client.delete(f"/v1/voice/{session}/audio", headers=student(OWNER)).status_code == 204
    assert not any(kept.path_for(session, t).exists() for t in turns)
    assert client.get(f"/v1/voice/{session}/audio", headers=student(OWNER)).json() == []


def test_only_a_wav_is_kept(client):
    r = keep(client, uuid.uuid4(), uuid.uuid4(), body=b"not audio")
    assert r.status_code == 422
