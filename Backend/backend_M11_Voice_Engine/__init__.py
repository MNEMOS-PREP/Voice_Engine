"""M11 — Voice & Conversation Engine.

Spec: plan_in_depth/M11_Voice_Engine.md, Revision 2 (§0): browser-first and
free. The interviewer's voice runs in the browser — `@ai/core`'s
`useInterviewerVoice`, which is this module's code living in core because more
than one module speaks. This package is the server half: what has to outlive a
page (the latency ledger, stored audio, misheard flags) and what a browser
cannot do (server ASR with word timestamps).
"""

MODULE_ID = "M11"

__all__ = ["MODULE_ID"]
