"""M11 — Voice & Conversation Engine · standalone application.

Runs this module ALONE on its reserved port:

    uvicorn backend_M11_Voice_Engine.app:app --reload --port 8111

Ports: PORTS.txt (API 8111, web 5211, and 8211 reserved for the WebSocket the
spec's control channel will need). Nothing upstream is needed to boot;
`/v1/deps` says whether M06 is up.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from ai_core.db import create_all, engine
from ai_core.modules_meta import ModuleStatus, module_status
from ai_core.schema_repair import ensure_schema
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import MODULE_ID, tts
from .keys import load_keys
from .router import router

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # keys.txt (beside the repos, shared with every module) into the
    # environment — names logged, never values. Server recognition reads it.
    load_keys()
    # create_all() makes missing TABLES and ignores existing ones, so a model
    # that gained a field leaves an older dev.db one column short; and
    # ensure_schema() adds those columns, additively.
    create_all()
    for change in ensure_schema(engine):
        log.info("schema: added missing column %s", change)
    # The voice model loads in the background (~20 s once downloaded); the
    # module answers meanwhile, and /v1/voice/engine says "loading".
    tts.engine().start()
    log.info("M11 ready")
    yield


app = FastAPI(title="M11 — Voice & Conversation Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "module": MODULE_ID}


@app.get("/status", response_model=ModuleStatus, tags=["meta"])
def status() -> ModuleStatus:
    return module_status(MODULE_ID)
