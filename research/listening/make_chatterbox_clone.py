"""Is a cloned real conversational voice more human? — the dataset-voice test.

Clones each of DailyTalk's two speakers (Lee et al., ICASSP 2023; recorded
for conversational TTS research; CC BY-SA 4.0, academic use) from ~12 s of
their OWN conversational turns, and speaks the interviewer lines with it.

Research use only, kept on this laptop: a dataset licence is not a speaker's
consent to become a product's interviewer (spec FR-11.21; Hugging Face,
"Voice cloning with consent"). This answers "does it sound more human?" —
not "may we ship it?".

    <scratch venv>\\Scripts\\python make_chatterbox_clone.py
"""

from __future__ import annotations

import json
import pathlib
import time

import torch
import torchaudio

from chatterbox.tts_turbo import ChatterboxTurboTTS
from make_chatterbox import LINES

HERE = pathlib.Path(__file__).resolve().parent
REF = HERE / "reference"
SPOKEN = ["greeting_spoken", "question_spoken", "followup_sounds"]


def reference_for(speaker: str, seconds: float = 12.0) -> pathlib.Path:
    """The speaker's own turns, joined with a short breath of silence."""
    pieces, total, rate = [], 0.0, None
    for clip in sorted(REF.glob(f"dailytalk_spk{speaker}_*.wav")):
        wav, sr = torchaudio.load(str(clip))
        if rate is None:
            rate = sr
        if sr != rate:
            wav = torchaudio.functional.resample(wav, sr, rate)
        pieces += [wav.mean(0, keepdim=True), torch.zeros(1, int(0.25 * rate))]
        total += wav.shape[-1] / rate
        if total >= seconds:
            break
    out = REF / f"reference_spk{speaker}.wav"
    torchaudio.save(str(out), torch.cat(pieces, dim=-1), rate)
    print(f"reference speaker {speaker}: {total:.1f}s from DailyTalk")
    return out


def main() -> None:
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    made = []
    for speaker in ("0", "1"):
        ref = reference_for(speaker)
        model.prepare_conditionals(str(ref))
        for line_id in SPOKEN:
            t0 = time.perf_counter()
            wav = model.generate(LINES[line_id])
            took = time.perf_counter() - t0
            seconds = wav.shape[-1] / model.sr
            name = f"chatterbox_clone_dailytalk{speaker}_{line_id}.wav"
            torchaudio.save(str(HERE / name), wav, model.sr)
            made.append(
                {"file": name, "speaker": speaker, "line": line_id, "text": LINES[line_id],
                 "audio_s": round(seconds, 2), "took_s": round(took, 2), "rtf": round(took / seconds, 2)}
            )
            print(f"{name}: {seconds:.1f}s in {took:.1f}s (RTF {took / seconds:.2f})", flush=True)
    (HERE / "chatterbox_clone.json").write_text(json.dumps({"clips": made}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
