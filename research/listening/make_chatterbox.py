"""Listening-test clips from Chatterbox Turbo (Resemble AI, MIT), on this CPU.

Free and fully offline: no key, no account, nothing sent anywhere. Uses the
model's BUILT-IN voice — no real person is cloned. Every clip also times
itself, because "can a student's laptop do this live?" is half the question.

    <scratch venv>\\Scripts\\python make_chatterbox.py

Writes chatterbox_*.wav and chatterbox.json beside this file (*.wav is
gitignored). Chatterbox watermarks every clip (Perth) by design.
"""

from __future__ import annotations

import json
import pathlib
import time

import torch
import torchaudio

from chatterbox.tts_turbo import ChatterboxTurboTTS

HERE = pathlib.Path(__file__).resolve().parent

# The same lines as make_samples.py: as the interviewer writes them today,
# and rewritten for the ear — plus the human sounds Turbo can perform.
LINES = {
    "greeting_written": "Hi, I'm Meera, thanks for making the time. We'll keep this conversational. Let's start with something easy.",
    "greeting_spoken": "Hi! I'm Meera. Thanks for making the time. So, we'll keep this pretty relaxed, okay? Let's start with something easy.",
    "question_written": "Two keys hash to the same bucket. Walk me through how a hash map can handle that, and what it costs.",
    "question_spoken": "Okay, so. Say two keys land in the same bucket. How would a hash map deal with that? And, um, what does it cost you?",
    "followup_spoken": "Hmm, right, chaining. And if one bucket just keeps getting longer, what happens to your lookups?",
    "followup_sounds": "[chuckle] Right, chaining, the classic. Okay. And if one bucket just keeps getting longer, what happens to your lookups?",
}


def main() -> None:
    torch.set_num_threads(max(1, (torch.get_num_threads() or 8)))
    started = time.perf_counter()
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    load_s = time.perf_counter() - started
    print(f"loaded in {load_s:.1f}s, threads={torch.get_num_threads()}")

    made = []
    for line_id, text in LINES.items():
        t0 = time.perf_counter()
        wav = model.generate(text)
        took = time.perf_counter() - t0
        seconds = wav.shape[-1] / model.sr
        name = f"chatterbox_turbo_{line_id}.wav"
        torchaudio.save(str(HERE / name), wav, model.sr)
        made.append(
            {
                "file": name,
                "line": line_id,
                "text": text,
                "audio_s": round(seconds, 2),
                "took_s": round(took, 2),
                "rtf": round(took / seconds, 2) if seconds else None,
            }
        )
        print(f"{name}: {seconds:.1f}s of audio in {took:.1f}s (RTF {took / seconds:.2f})")

    (HERE / "chatterbox.json").write_text(
        json.dumps({"model": "ResembleAI/chatterbox-turbo", "load_s": round(load_s, 1), "clips": made}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
