"""M11's `/v1` surface (spec §7).

The identity guard is on the router, so it runs on every route below and on
every route added later (`access.py`).

Every path's first segment after `/v1` is `voice`: Platform_Shell proxies one
origin by that segment, and `voice` is this module's alone (the shell's
`vite.config.ts`, checked by `tests/test_scaffold.py`). `deps` is the one path
every module serves.
"""

from __future__ import annotations

from ai_core.dependencies import DependencyStatus
from fastapi import APIRouter, Depends

from .access import enforce_access
from .dependencies import deps

router = APIRouter(prefix="/v1", dependencies=[Depends(enforce_access)])


@router.get("/deps", response_model=list[DependencyStatus], tags=["meta"])
def dependencies(force: bool = False) -> list[DependencyStatus]:
    """Each upstream, whether it is up, and the sentence a student sees if not."""
    return deps().statuses(force=force)


__all__ = ["router"]
