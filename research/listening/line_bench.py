# Run from Backend: PYTHONPATH=. .venvScriptspython ..esearchisteningine_bench.py 3 plan
"""A line as the room hears it: planned at once, asked for in order, played back to back.

usage: python line_bench.py [ROWS] [plan|noplan]
Prints, per piece: when it was ready, when it starts playing, and the gap before it.
"""

import io
import os
import sys
import tempfile
import time
import wave

os.environ["M11_TTS_CACHE"] = tempfile.mkdtemp(prefix="m11-bench-")
if len(sys.argv) > 1:
    os.environ["M11_TTS_ROWS"] = sys.argv[1]
PLAN = (sys.argv[2] if len(sys.argv) > 2 else "plan") == "plan"

from backend_M11_Voice_Engine import tts  # noqa: E402

SHORT = [
    "Thanks, that makes sense.",
    "What would you change about the harness",
    "if you rebuilt it today?",
]
LINE = SHORT if os.getenv("LINE") == "short" else [
    "Let's practise defending one line from your resume.",
    "Two minutes, no score.",
    "Let's start with something easy.",
    "Can you describe, in your own words,",
    "what the automated evaluation harness you built does,",
    "and what problem it was intended to solve?",
]

engine = tts.Engine(tts.Cast.load())
engine.start()
while engine.state == "loading":
    time.sleep(0.5)
assert engine.state == "ready", engine.reason
voice = engine.cast.resolve(persona_id="friendly_recruiter")
print(f"rows={tts.ROWS} threads={tts.THREADS} plan={PLAN}", flush=True)

t0 = time.perf_counter()
if PLAN:
    engine.plan([(s, voice) for s in LINE], "bench")
clock = None
total_gap = 0.0
speech = 0.0
for text in LINE:
    data, cached, _ = engine.speak(text, voice, line="bench")
    ready = time.perf_counter() - t0
    with wave.open(io.BytesIO(data)) as w:
        seconds = w.getnframes() / w.getframerate()
    speech += seconds
    if clock is None:
        start, note = ready, "first audio"
    else:
        start = max(ready, clock)
        gap = start - clock
        total_gap += gap
        note = f"gap {gap:.1f}s" if gap > 0.05 else "no gap"
    clock = start + seconds
    print(f"  ready {ready:5.1f}s  plays {start:5.1f}-{clock:5.1f}s ({seconds:.1f}s)  {note}  | {text}", flush=True)
print(f"speech {speech:.1f}s, finished at {clock:.1f}s, gaps after the first audio {total_gap:.1f}s", flush=True)
