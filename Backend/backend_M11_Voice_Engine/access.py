"""Who is asking — on `ai_core.guard`, declared once on the ROUTER.

Identity before endpoints (TODO §7, step 2): the guard runs on every route,
including the ones nobody has written yet. A per-route check is the one
somebody omits on the sixteenth endpoint, and the sixteenth endpoint is the one
that leaks — and what this module will hold is a student's own voice.

Ways a route here names a student, as they arrive:

    /candidates/{candidate_id}/…   the path — handled by the shared guard
    ?candidate=…                   the query — handled by the shared guard
    a body naming a candidate      `require_candidate` in the handler

The voice routes to come (`/v1/voice/{session_id}/…`) name an interview, which
belongs to a student; they add an `owners` resolver for `session_id` here when
the first of them lands, so `may_see` is asked about the right person.
"""

from __future__ import annotations

from ai_core.guard import candidate_guard, identity_headers, require_candidate

enforce_access = candidate_guard()

__all__ = ["enforce_access", "identity_headers", "require_candidate"]
