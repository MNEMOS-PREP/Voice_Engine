"""The module's frame: it boots alone, its manifest keeps Rule 2, its nouns are
its own in the shell, and its guard is on every route (TODO §7, steps 1–2)."""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from ai_core.testing import assert_refuses_strangers

from backend_M11_Voice_Engine import MODULE_ID
from backend_M11_Voice_Engine.app import app
from backend_M11_Voice_Engine.dependencies import MANIFEST

SHELL = pathlib.Path(__file__).resolve().parents[4] / "Platform_Shell" / "vite.config.ts"
#: Every module answers /v1/deps for itself; the shell routes it by screen.
SHARED = {"deps"}


def test_it_boots_alone_and_says_who_it_is(client):
    assert client.get("/health").json() == {"status": "ok", "module": "M11"}
    assert client.get("/status").json()["id"] == MODULE_ID


@pytest.mark.gate
def test_manifest_declares_every_upstream_optional_with_a_sentence():
    """Voice is never the only way through an interview (FR-11.18), so no
    upstream may be required — someone else's outage would become ours."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["module"] == "M11"
    assert manifest["repo"].endswith("/Voice_Engine")
    assert manifest["ports"] == {"backend": 8111, "frontend": 5211}
    for dep in manifest["depends_on"]:
        assert dep["required"] is False, f"{dep['module']} would make its outage ours"
        assert dep["on_missing"].strip(), f"{dep['module']} has nothing to tell a student"
        # launch.ps1 finds siblings by the last segment of this URL.
        assert dep["repo"].rstrip("/").split("/")[-1], dep["module"]


def test_deps_names_m06_and_what_its_absence_costs(client):
    """Nothing is listening in a test, so M06 reads as down — and the row
    still carries the sentence a student would be shown."""
    rows = client.get("/v1/deps").json()
    assert [r["module_id"] for r in rows] == ["M06"]
    assert rows[0]["available"] is False


def shell_owners() -> dict[str, str]:
    text = SHELL.read_text(encoding="utf-8")
    start = text.index("const OWNER")
    table = text[start : text.index("};", start)]
    return dict(re.findall(r'^\s*"?([a-z-]+)"?:\s*"(m\d\d)"', table, flags=re.M))


@pytest.mark.gate
@pytest.mark.skipif(not SHELL.exists(), reason="Platform_Shell is not checked out next door")
def test_every_m11_noun_is_routed_to_m11():
    """Platform_Shell proxies one origin by the first segment after /v1. Read
    from the shell's own config rather than a copy, which is one change behind
    the day it is taken."""
    owners = shell_owners()
    nouns = {
        path.split("/")[2]
        for path in app.openapi()["paths"]
        if path.startswith("/v1/") and path.split("/")[2] not in SHARED
    }
    wrong = {noun: owners.get(noun, "nobody") for noun in nouns if owners.get(noun) != "m11"}
    assert not wrong, f"M11 serves nouns the shell routes elsewhere: {wrong}"
    assert owners.get("voice") == "m11", "the shell does not route /v1/voice to M11"


@pytest.mark.gate
def test_every_route_that_names_a_student_refuses_strangers(client):
    """Platform_Core's own check, on the router-level guard: every route whose
    path or query names a student, asked as nobody and as another student.
    None exist yet; the check is here from the first commit so the first one
    that does is held to it without anyone remembering to add it."""
    assert_refuses_strangers(client, app, expect_at_least=0)


def test_the_guard_is_on_the_router_not_on_each_route():
    """Declared once, so a route added tomorrow cannot be written without it."""
    from backend_M11_Voice_Engine.access import enforce_access
    from backend_M11_Voice_Engine.router import router

    assert any(d.dependency is enforce_access for d in router.dependencies)
