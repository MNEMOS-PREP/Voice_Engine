"""Does each clip say what it was asked to? Whisper (Groq) reads every clip
back, and the words are compared with the line it was given.

Voice-cloning models can skip, repeat or garble words — a clip that sounds
human but says the wrong thing is a worse interviewer, not a better one.
Only synthetic clips are sent; no student audio. Writes words.json.

    ..\\..\\Backend\\.venv\\Scripts\\python check_words.py
"""

from __future__ import annotations

import difflib
import json
import pathlib
import re
import uuid
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
KEYS = HERE.parents[2] / "keys.txt"


def groq_key() -> str:
    for raw in KEYS.read_text(encoding="utf-8").splitlines():
        name, _, value = raw.partition("=")
        if name.strip() == "GROQ_API_KEYS":
            return value.split(",")[0].strip().strip('"')
    raise SystemExit("GROQ_API_KEYS not in keys.txt")


def transcribe(key: str, path: pathlib.Path) -> str:
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-large-v3-turbo\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nen\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: audio/wav\r\n\r\n',
    ]
    body = "".join(parts).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "mnemos-voice-engine/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())["text"]


def words(text: str) -> list[str]:
    text = re.sub(r"\[[^\]]+\]|<[^>]+>", " ", text.lower())
    return re.findall(r"[a-z']+", text)


def main() -> None:
    key = groq_key()
    clips = []
    for manifest in ("chatterbox.json", "chatterbox_clone.json", "samples.json", "gemini.json"):
        path = HERE / manifest
        if path.exists():
            clips += [c for c in json.loads(path.read_text(encoding="utf-8"))["clips"] if (HERE / c["file"]).exists()]
    results = []
    for clip in clips:
        heard = transcribe(key, HERE / clip["file"])
        want, got = words(clip["text"]), words(heard)
        ratio = difflib.SequenceMatcher(a=want, b=got).ratio()
        results.append({"file": clip["file"], "match": round(ratio, 3), "heard": heard.strip()})
        flag = "" if ratio >= 0.9 else "   <-- check"
        print(f"{ratio:5.2f}  {clip['file']}{flag}\n       heard: {heard.strip()}")
    (HERE / "words.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
