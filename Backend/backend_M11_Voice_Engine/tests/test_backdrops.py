"""The rooms behind the interviewers (2026-10-21): listed, served, and never
a path outside their folders."""

from __future__ import annotations

from backend_M11_Voice_Engine import backdrops


def _room(folder, name: str, body: bytes = b"RIFF0000WEBPVP8 ") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.webp").write_bytes(body)


def test_the_list_holds_the_shared_rooms_then_this_machines_own(client, tmp_path, monkeypatch):
    monkeypatch.setattr(backdrops, "BACKDROPS_DIR", tmp_path)
    _room(tmp_path, "stocksnap-living-room-01")
    _room(tmp_path, "wikimedia-office-02")
    _room(tmp_path / "local", "mine-01")
    (tmp_path / "notes.txt").write_text("not a room")
    body = client.get("/v1/voice/backdrops").json()
    assert [b["name"] for b in body["backdrops"]] == [
        "stocksnap-living-room-01",
        "wikimedia-office-02",
        "mine-01",
    ]
    assert body["backdrops"][2]["url"] == "/v1/voice/backdrops/mine-01.webp"


def test_a_room_is_served_with_a_tag_and_a_304_when_unchanged(client, tmp_path, monkeypatch):
    monkeypatch.setattr(backdrops, "BACKDROPS_DIR", tmp_path)
    _room(tmp_path / "local", "mine-01", b"RIFF1234WEBPVP8 room")
    first = client.get("/v1/voice/backdrops/mine-01.webp")
    assert first.status_code == 200 and first.headers["content-type"] == "image/webp"
    assert first.content.endswith(b"room")
    again = client.get(
        "/v1/voice/backdrops/mine-01.webp", headers={"If-None-Match": first.headers["etag"]}
    )
    assert again.status_code == 304


def test_nothing_outside_the_folders_and_no_odd_names(client, tmp_path, monkeypatch):
    monkeypatch.setattr(backdrops, "BACKDROPS_DIR", tmp_path / "rooms")
    _room(tmp_path, "outside")
    assert client.get("/v1/voice/backdrops/outside.webp").status_code == 404
    assert client.get("/v1/voice/backdrops/..%2Foutside.webp").status_code in (404, 422)
    assert backdrops.path_of("../outside") is None
    assert client.get("/v1/voice/backdrops").json() == {"backdrops": []}
