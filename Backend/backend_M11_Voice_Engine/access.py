"""Who is asking — on `ai_core.guard`, declared once on the ROUTER.

Identity before endpoints (TODO §7, step 2): the guard runs on every route,
including the ones nobody has written yet. A per-route check is the one
somebody omits on the sixteenth endpoint, and the sixteenth endpoint is the one
that leaks — and what this module will hold is a student's own voice.

Ways a route here names a student:

    /voice/{session_id}/…          an interview, which belongs to a student —
                                   resolved below, then `may_see` is asked
    /candidates/{candidate_id}/…   the path — handled by the shared guard
    ?candidate=…                   the query — handled by the shared guard

**Whose interview is it?** M06 knows; M11 is not asked to call it on every
line. The student who posts an interview's first line owns its ledger, and
every later request is held to that student — a stranger posting to, or
reading, someone else's interview gets the guard's 403. An interview id is a
UUID handed to its own student only, so the first post is that student's.

Service callers forward the student's identity (`identity_headers`); there is
no `service` role.
"""

from __future__ import annotations

import uuid

from ai_core.db import get_session
from ai_core.guard import candidate_guard, identity_headers, require_candidate
from ai_core.identity import Principal
from fastapi import Depends, Request
from sqlmodel import Session, select

from .models import LineTiming


def interview_owner(db: Session, session_id: str) -> str | None:
    """The student whose interview this is, from its first recorded line."""
    try:
        sid = uuid.UUID(str(session_id))
    except ValueError:
        return None
    first = db.exec(
        select(LineTiming.candidate_id)
        .where(LineTiming.session_id == sid, LineTiming.candidate_id.is_not(None))  # type: ignore[union-attr]
        .order_by(LineTiming.recorded_at)
        .limit(1)
    ).first()
    return first


def enforce_access(request: Request, db: Session = Depends(get_session)) -> Principal | None:
    """`candidate_guard`, with interview ids resolved to their student."""
    return candidate_guard({"session_id": lambda sid: interview_owner(db, sid)})(request)


__all__ = ["enforce_access", "identity_headers", "interview_owner", "require_candidate"]
