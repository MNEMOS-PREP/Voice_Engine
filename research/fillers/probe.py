"""Does the recogniser keep "um" and "uh"? — M11, 2026-10-23.

M06's delivery notes count vocal fillers from the transcript, and Whisper
usually leaves them out, so a student who says "um" every third word was
told nothing (M06_OVERHAUL.md, limitations). OpenAI's guidance for Whisper:
it tends to skip filler words, and a prompt WRITTEN with fillers keeps them,
because the prompt sets the style it continues.

Before changing anything, this measures it on audio that really has them:
DisfluencySpeech (AMAAI Lab, SUTD; Apache-2.0, `amaai-lab/DisfluencySpeech`),
conversational speech whose annotated transcripts mark every filled pause
(`{F uh, }`), so each clip's true count is known. Three prompts, all opening
with the question as M11 sends it today:

- `today`: M11's prompt — "Interview question: …".
- `openai`: today's, then OpenAI's example line, fillers and all.
- `plain`: today's, then a shorter line with "um" and "uh" only (no "like",
  which M06 counts as a filler too).

Scored per prompt: fillers kept (of the true count), fillers invented on
clips that have none, word error rate on everything else (does the content
suffer?), and whether the style line is read back. Silence is sent too —
Whisper's known failure is writing its prompt over nothing. Hindi detection
(FR-11.22, `../codeswitch`) is checked again with the chosen prompt, against
that probe's own results.

One Groq key, paced under its 20 requests a minute; a 429 waits, it never
moves to another key. Run with M11's venv:
    ..\\..\\Backend\\.venv\\Scripts\\python.exe probe.py
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "Backend"))

from backend_M11_Voice_Engine.keys import keys_from_env, load_keys  # noqa: E402

DATASET = "amaai-lab/DisfluencySpeech"
AGENT = "AI-Interviewer/1.0 (+https://github.com/MNEMOS-PREP)"
URL = "https://api.groq.com/openai/v1/audio/transcriptions"
CACHE = HERE / "cache"
CODESWITCH = HERE.parent / "codeswitch"
ENGLISH = HERE.parent / "wer" / "cache"
QUESTION = "Interview question: Tell me about a project you built and the choices you made."
PROMPTS = {
    "today": QUESTION,
    "openai": QUESTION + " Umm, let me think like, hmm... Okay, here's what I'm, like, thinking.",
    "plain": QUESTION + " Um, so, uh, let me think. Uh, okay, um, here's what I did.",
}
READ_BACK = re.compile(r"let me think|here's what i'm|here's what i did", re.I)
#: The vocal fillers M06 counts (`delivery._VOCAL`), less "ah" and "hmm".
VOCAL = frozenset({"um", "umm", "uhm", "uh", "uhh", "er", "erm"})
PACE_S = 3.2
WITH_FILLERS = 30
WITHOUT = 10


def split_rows(split: str = "test", size: int = 250) -> list[dict]:
    """The whole split, a page at a time (the server's `/filter` timed out)."""
    out: list[dict] = []
    for offset in range(0, size, 100):
        params = urllib.parse.urlencode(
            {"dataset": DATASET, "config": "default", "split": split, "offset": offset,
             "length": min(100, size - offset)}
        )
        request = urllib.request.Request(
            f"https://datasets-server.huggingface.co/rows?{params}", headers={"User-Agent": AGENT}
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            rows = json.loads(response.read())["rows"]
        out.extend(
            {
                "id": f"{split}_{r['row_idx']}",
                "src": r["row"]["audio"][0]["src"],
                "reference": r["row"]["transcript_a"],
                "annotated": r["row"]["transcript_annotated"],
            }
            for r in rows
        )
    return out


def audio(item: dict) -> bytes:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{item['id']}.wav"
    if not path.exists():
        request = urllib.request.Request(item["src"], headers={"User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def silence(seconds: float, noise: float) -> bytes:
    rng = np.random.default_rng(7)
    x = rng.normal(0.0, noise, int(16000 * seconds)).astype(np.float32)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return out.getvalue()


_last = [0.0]


def hear(key: str, data: bytes, prompt: str) -> dict:
    boundary = uuid.uuid4().hex
    fields = [
        ("model", "whisper-large-v3-turbo"),
        ("response_format", "verbose_json"),
        ("temperature", "0"),
        ("prompt", prompt),
    ]
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'
        for n, v in fields
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    )
    body = "".join(parts).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    for attempt in range(8):
        wait = PACE_S - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        request = urllib.request.Request(
            URL,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = json.loads(response.read())
                segments = raw.get("segments") or []
                return {
                    "language": raw.get("language"),
                    "text": raw.get("text", "").strip(),
                    "no_speech": max((s.get("no_speech_prob", 0) for s in segments), default=None),
                }
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 7:
                raise
            time.sleep(float(exc.headers.get("retry-after") or 10) + 1)
    raise RuntimeError("unreachable")


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower().replace("-", " "))


def fillers(text: str) -> int:
    return sum(1 for w in words(text) if w in VOCAL)


def content(text: str) -> list[str]:
    return [w for w in words(text) if w not in VOCAL]


def errors(ref: list[str], hyp: list[str]) -> int:
    """Word-level edit distance."""
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[len(hyp)]


def main() -> None:
    load_keys()
    keys = keys_from_env("GROQ_API_KEYS", "GROQ_API_KEY")
    if not keys:
        raise SystemExit("No Groq key in keys.txt.")
    key = keys[0]  # one key: no moving to another organisation's quota
    every = split_rows()
    # Filled pauses are marked `{F uh, }` / `{F um, }`; clips with none of any
    # kind are the control for fillers the prompt might invent.
    marked = [r for r in every if fillers(r["reference"]) and "{F u" in r["annotated"]]
    marked = marked[:WITH_FILLERS]
    plain = [r for r in every if "{F " not in r["annotated"] and not fillers(r["reference"])]
    plain = plain[:WITHOUT]
    clips = [("fillers", item) for item in marked] + [("none", item) for item in plain]
    rows: list[dict] = []
    for kind, item in clips:
        data = audio(item)
        for name, prompt in PROMPTS.items():
            got = hear(key, data, prompt)
            rows.append(
                {
                    "kind": kind,
                    "clip": item["id"],
                    "prompt": name,
                    "reference": item["reference"],
                    "text": got["text"],
                    "fillers_true": fillers(item["reference"]),
                    "fillers_heard": fillers(got["text"]),
                    "errors": errors(content(item["reference"]), content(got["text"])),
                    "words": len(content(item["reference"])),
                    "read_back": bool(READ_BACK.search(got["text"])),
                }
            )
            print(f"{kind:7} {item['id']:10} {name:6} {fillers(got['text'])}/"
                  f"{fillers(item['reference'])}  {got['text'][:80]!r}")
    for label, data in (("silence", silence(3, 0.0005)), ("room noise", silence(3, 0.01))):
        for name, prompt in PROMPTS.items():
            got = hear(key, data, prompt)
            rows.append({"kind": "silence", "clip": label, "prompt": name, "text": got["text"],
                         "no_speech": got["no_speech"],
                         "read_back": bool(READ_BACK.search(got["text"]))})
            print(f"silence {label:10} {name:6} {got['text']!r} no_speech={got['no_speech']}")
    # FR-11.22 again, with the line most likely to be chosen: detection must
    # still hear Hindi as Hindi and leave English word for word.
    baseline = {
        (r["clip"]): r for r in json.loads((CODESWITCH / "probe.json").read_text(encoding="utf-8"))
        if r["setting"] == "auto" and r["kind"] in ("hindi", "english")
    }
    for clip, before in baseline.items():
        path = (CODESWITCH / "cache" / f"{clip}.wav") if clip.startswith("hi_") else (
            ENGLISH / f"{clip}.wav"
        )
        if not path.exists():
            continue
        got = hear(key, path.read_bytes(), PROMPTS["plain"])
        rows.append({"kind": "language", "clip": clip, "prompt": "plain",
                     "detected_before": before["detected"], "detected": got["language"],
                     "text_before": before["text"], "text": got["text"],
                     "read_back": bool(READ_BACK.search(got["text"]))})
        print(f"language {clip:22} {before['detected']} -> {got['language']}  {got['text'][:70]!r}")
    (HERE / "probe.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")


#: The confirmation (second run): the winner, `plain`, against the same line
#: without "here's what I did" — over silence the first run wrote "…see what I
#: did", the line's own words — on the NEXT 30 clips, so the choice is not
#: fitted to the first 30.
CONFIRM = {
    "plain": PROMPTS["plain"],
    "short": QUESTION + " Um, so, uh, let me think. Uh, okay, um.",
}


def confirm() -> None:
    load_keys()
    key = keys_from_env("GROQ_API_KEYS", "GROQ_API_KEY")[0]
    every = split_rows()
    marked = [r for r in every if fillers(r["reference"]) and "{F u" in r["annotated"]]
    marked = marked[WITH_FILLERS : 2 * WITH_FILLERS]
    plain = [r for r in every if "{F " not in r["annotated"] and not fillers(r["reference"])]
    plain = plain[:WITHOUT]
    rows: list[dict] = []
    for kind, item in [("fillers", i) for i in marked] + [("none", i) for i in plain]:
        data = audio(item)
        for name, prompt in CONFIRM.items():
            got = hear(key, data, prompt)
            rows.append({"kind": kind, "clip": item["id"], "prompt": name, "text": got["text"],
                         "fillers_true": fillers(item["reference"]),
                         "fillers_heard": fillers(got["text"]),
                         "errors": errors(content(item["reference"]), content(got["text"])),
                         "words": len(content(item["reference"])),
                         "read_back": bool(READ_BACK.search(got["text"]))})
            print(f"{kind:7} {item['id']:10} {name:6} {fillers(got['text'])}/"
                  f"{fillers(item['reference'])}  {got['text'][:80]!r}")
    for label, data in (("silence", silence(3, 0.0005)), ("room noise", silence(3, 0.01))):
        for name, prompt in CONFIRM.items():
            got = hear(key, data, prompt)
            rows.append({"kind": "silence", "clip": label, "prompt": name, "text": got["text"]})
            print(f"silence {label:10} {name:6} {got['text']!r}")
    (HERE / "confirm.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    confirm() if sys.argv[1:] == ["confirm"] else main()
