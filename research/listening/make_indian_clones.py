"""Six Indian-English voices, cloned from IndicTTS (IIT Madras, CC BY 4.0).

The user's verdict on 2026-10-05: Chatterbox and the DailyTalk clones were
close; the roster should mix Indian and foreign accents, mostly Indian. These
are the Indian candidates — picked by pick_voices.py as the most mutually
different of the corpus's distinct voices, three higher and three lower.

IndicTTS was recorded by native speakers FOR speech synthesis, so a clone is
within what the recordings were made for; CC BY 4.0 asks for the credit
"IndicTTS, SMT Lab, IIT Madras" wherever the voice is used.

    <scratch venv>\\Scripts\\python make_indian_clones.py
"""

from __future__ import annotations

import json
import pathlib
import time

import torchaudio

from chatterbox.tts_turbo import ChatterboxTurboTTS
from make_chatterbox import LINES

HERE = pathlib.Path(__file__).resolve().parent
REF = HERE / "reference"

# A greeting with no name in it, so a voice is not heard saying someone else's.
SAY = {
    "greeting_neutral": "Hi! Thanks for making the time. So, we'll keep this pretty relaxed, okay? Let's start with something easy.",
    "question_spoken": LINES["question_spoken"],
    "followup_sounds": LINES["followup_sounds"],
}


def main() -> None:
    voices = [v for v in json.loads((REF / "voices.json").read_text(encoding="utf-8")) if v["picked"]]
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    made = []
    for n, voice in enumerate(sorted(voices, key=lambda v: (v["register"], v["pitch_hz"])), start=1):
        tag = voice["file"].removesuffix(".wav").replace("indictts_", "")
        label = f"Chatterbox Turbo · Indian voice {n} ({voice['register']}, {voice['pitch_hz']} Hz) · IndicTTS {tag}"
        model.prepare_conditionals(str(REF / voice["file"]))
        for line_id, text in SAY.items():
            t0 = time.perf_counter()
            wav = model.generate(text)
            took = time.perf_counter() - t0
            seconds = wav.shape[-1] / model.sr
            name = f"chatterbox_clone_indictts{tag}_{line_id}.wav"
            torchaudio.save(str(HERE / name), wav, model.sr)
            made.append({"file": name, "label": label, "line": line_id, "text": text,
                         "audio_s": round(seconds, 2), "took_s": round(took, 2), "rtf": round(took / seconds, 2)})
            print(f"{name}: {seconds:.1f}s in {took:.1f}s", flush=True)
    (HERE / "indian_clones.json").write_text(json.dumps({"clips": made}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
