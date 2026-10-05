"""Which IndicTTS samples are distinct people, and which to cast.

Chatterbox's own speaker encoder gives each reference a voice fingerprint;
samples whose fingerprints are near-identical are the same speaker. Median
pitch sorts the rest into lower and higher voices (the casting only needs
"sounds like a woman / a man" to match a persona's authored voice_id — it is
not a claim about anyone). Picks the most mutually different voices of each.

Writes reference/voices.json. Run with the Chatterbox venv.
"""

from __future__ import annotations

import json
import pathlib

import librosa
import numpy as np
import torch

from chatterbox.models.voice_encoder import VoiceEncoder

HERE = pathlib.Path(__file__).resolve().parent
REF = HERE / "reference"
SAME_SPEAKER = 0.86  # cosine similarity above which two samples are one voice
PICK_PER_GROUP = 3


def main() -> None:
    from safetensors.torch import load_file
    from huggingface_hub import snapshot_download

    ckpt = pathlib.Path(snapshot_download("ResembleAI/chatterbox-turbo", allow_patterns=["ve.safetensors"]))
    ve = VoiceEncoder()
    ve.load_state_dict(load_file(ckpt / "ve.safetensors"))
    ve.eval()

    samples = json.loads((REF / "indictts.json").read_text(encoding="utf-8"))
    rows = []
    for s in samples:
        wav, sr = librosa.load(REF / s["file"], sr=16000)
        wav = wav[: 16000 * 20]
        with torch.inference_mode():
            emb = ve.embeds_from_wavs([wav], sample_rate=16000)
        f0 = librosa.yin(wav, fmin=60, fmax=400, sr=16000)
        voiced = f0[(f0 > 60) & (f0 < 400)]
        rows.append({**s, "emb": np.asarray(emb).reshape(-1), "pitch_hz": float(np.median(voiced))})

    # Collapse near-identical fingerprints into one speaker.
    speakers: list[list[dict]] = []
    for r in rows:
        for group in speakers:
            sim = float(np.dot(r["emb"], group[0]["emb"]) / (np.linalg.norm(r["emb"]) * np.linalg.norm(group[0]["emb"])))
            if sim > SAME_SPEAKER:
                group.append(r)
                break
        else:
            speakers.append([r])
    print(f"{len(rows)} samples -> {len(speakers)} distinct voices")

    voices = []
    for group in speakers:
        best = max(group, key=lambda r: r["seconds"] if r["seconds"] <= 35 else 0)
        voices.append({**best, "same_as": [g["file"] for g in group if g is not best]})
    # A voice between the bands is left out of casting rather than guessed at.
    higher = sorted([v for v in voices if v["pitch_hz"] >= 175], key=lambda v: v["pitch_hz"])
    lower = sorted([v for v in voices if v["pitch_hz"] <= 150], key=lambda v: v["pitch_hz"])

    def spread(group: list[dict]) -> list[dict]:
        """Greedy: each next pick is the voice least like those already picked."""
        if not group:
            return []
        picked = [group[len(group) // 2]]
        while len(picked) < min(PICK_PER_GROUP, len(group)):
            def nearest(v):
                return max(float(np.dot(v["emb"], p["emb"]) / (np.linalg.norm(v["emb"]) * np.linalg.norm(p["emb"]))) for p in picked)
            picked.append(min((v for v in group if v not in picked), key=nearest))
        return picked

    chosen = spread(higher) + spread(lower)
    for v in voices:
        tag = "PICK" if v in chosen else "    "
        print(f"{tag} {v['file']}  pitch {v['pitch_hz']:5.0f} Hz  {v['seconds']:4.1f}s  (+{len(v['same_as'])} same)")
    out = [
        {"file": v["file"], "pitch_hz": round(v["pitch_hz"]), "register": "higher" if v["pitch_hz"] >= 175 else "lower" if v["pitch_hz"] <= 150 else "between",
         "seconds": v["seconds"], "picked": v in chosen}
        for v in voices
    ]
    (REF / "voices.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
