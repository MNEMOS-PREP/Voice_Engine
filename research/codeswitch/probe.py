"""What does the recogniser do with Hindi? — M11, FR-11.22 and EC-11.10.

M11 asks Whisper for English (`language=en`). The spec wants code-switching
tolerated without penalty: Hindi spoken in an answer kept as said, tagged,
and scored on content. Before changing anything, this measures three
settings on three kinds of audio:

- settings: `en` (today), no language (Whisper detects it), `hi`;
- audio: Hindi read speech (IndicTTS Hindi, IIT Madras, CC BY 4.0, the HF
  mirror `SPRINGLab/IndicTTS-Hindi`); Indian-accented English (day 6's
  IndicTTS English clips, `../wer/cache`); and the two joined — an English
  sentence then a Hindi one, the shape of a code-switched answer.

The questions: does detection keep English answers English, and what does
forcing English do to Hindi — transcribe it, translate it, or lose it?
Scored by detected language and how much of the text is in Devanagari (the
dataset's own Hindi text arrives with broken combining marks, so no
character error rate against it). Writes probe.json and prints a table.

Needs a Groq key in keys.txt. Run with M11's venv:
    ..\\..\\Backend\\.venv\\Scripts\\python.exe probe.py
"""

from __future__ import annotations

import io
import json
import pathlib
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

from backend_M11_Voice_Engine.keys import KeyRing, load_keys  # noqa: E402

DATASET = "SPRINGLab/IndicTTS-Hindi"
AGENT = "AI-Interviewer/1.0 (+https://github.com/MNEMOS-PREP)"
URL = "https://api.groq.com/openai/v1/audio/transcriptions"
CACHE = HERE / "cache"
ENGLISH = HERE.parent / "wer" / "cache"
PROMPT = "Interview question: Tell me about a project you built and the choices you made."
SETTINGS = {"en": "en", "auto": None, "hi": "hi"}


def rows(offsets: list[int]) -> list[dict]:
    out = []
    for offset in offsets:
        query = urllib.parse.urlencode(
            {
                "dataset": DATASET,
                "config": "default",
                "split": "train",
                "offset": offset,
                "length": 1,
            }
        )
        request = urllib.request.Request(
            f"https://datasets-server.huggingface.co/rows?{query}", headers={"User-Agent": AGENT}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            row = json.loads(response.read())["rows"][0]["row"]
        out.append({"offset": offset, "src": row["audio"][0]["src"]})
    return out


def audio(item: dict) -> bytes:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"hi_{item['offset']}.wav"
    if not path.exists():
        request = urllib.request.Request(item["src"], headers={"User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def mono16k(data: bytes) -> np.ndarray:
    """A WAV as 16 kHz mono floats, whatever it was recorded at."""
    with wave.open(io.BytesIO(data)) as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    kind = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=kind).astype(np.float32)
    if width == 1:
        x = x - 128
    x = x.reshape(-1, channels).mean(axis=1) / float(2 ** (8 * width - 1))
    if rate != 16000:
        n = int(len(x) * 16000 / rate)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return x


def as_wav(x: np.ndarray) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return out.getvalue()


def joined(first: bytes, second: bytes) -> bytes:
    """Two recordings, one after the other with 400 ms between."""
    return as_wav(np.concatenate([mono16k(first), np.zeros(6400, np.float32), mono16k(second)]))


def hear(ring: KeyRing, data: bytes, language: str | None) -> dict:
    boundary = uuid.uuid4().hex
    fields = [
        ("model", "whisper-large-v3-turbo"),
        ("response_format", "verbose_json"),
        ("temperature", "0"),
        ("prompt", PROMPT),
    ]
    if language:
        fields.append(("language", language))
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
        request = urllib.request.Request(
            URL,
            data=body,
            headers={
                "Authorization": f"Bearer {ring.next()}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = json.loads(response.read())
                return {"language": raw.get("language"), "text": raw.get("text", "").strip()}
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 7:
                raise
            time.sleep(float(exc.headers.get("retry-after") or 10) + 1)
    raise RuntimeError("unreachable")


def devanagari(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(1 for c in letters if "ऀ" <= c <= "ॿ") / max(1, len(letters))


def main() -> None:
    load_keys()
    ring = KeyRing.from_env("GROQ_API_KEYS", "GROQ_API_KEY")
    hindi = rows([0, 37, 211, 512, 1024, 2048, 3001, 4096])
    english = sorted(ENGLISH.glob("*.wav"))[::12][:8]
    clips: list[tuple[str, str, bytes]] = []
    for item in hindi:
        clips.append(("hindi", f"hi_{item['offset']}", as_wav(mono16k(audio(item)))))
    for path in english:
        clips.append(("english", path.stem, path.read_bytes()))
    for item, path in zip(hindi[:4], english[:4], strict=False):
        clips.append(
            ("mixed", f"{path.stem}+hi_{item['offset']}", joined(path.read_bytes(), audio(item)))
        )
    out = []
    for kind, name, data in clips:
        for setting, language in SETTINGS.items():
            got = hear(ring, data, language)
            out.append(
                {
                    "kind": kind,
                    "clip": name,
                    "setting": setting,
                    "detected": got["language"],
                    "text": got["text"],
                    "devanagari": round(devanagari(got["text"]), 2),
                }
            )
            print(f"{kind:8} {name:22} {setting:5} {str(got['language']):9} {got['text'][:90]!r}")
    (HERE / "probe.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
