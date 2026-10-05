"""Indian-English reference voices from IndicTTS (IIT Madras), for cloning.

IndicTTS — SMT Lab, IIT Madras; a MeitY-funded consortium; English recorded
by native speakers of Indian languages FOR speech synthesis; CC BY 4.0
(attribution: "IndicTTS, SMT Lab, IIT Madras"). Read from the IIT Madras
SPRING Lab's Hugging Face mirror, `SPRINGLab/IndicTTS-English`, which has
151,640 utterances and no speaker labels — so this samples three consecutive
utterances at evenly spaced offsets (the corpus is stored speaker by speaker)
and keeps one ~10 s reference per distinct voice.

Writes reference/indictts_<offset>.wav and reference/indictts.json.
Run with the Chatterbox venv (it needs torchaudio).
"""

from __future__ import annotations

import io
import json
import pathlib
import time
import urllib.parse
import urllib.request

import torch
import torchaudio

HERE = pathlib.Path(__file__).resolve().parent
REF = HERE / "reference"
DATASET = "SPRINGLab/IndicTTS-English"
TOTAL = 151_640
POINTS = 30
PER_POINT = 4


def rows(offset: int, length: int) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "train", "offset": offset, "length": length}
    )
    request = urllib.request.Request(
        f"https://datasets-server.huggingface.co/rows?{query}",
        headers={"User-Agent": "mnemos-voice-engine/0.1"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())["rows"]


def fetch(url: str) -> tuple[torch.Tensor, int]:
    request = urllib.request.Request(url, headers={"User-Agent": "mnemos-voice-engine/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    wav, sr = torchaudio.load(io.BytesIO(data))
    return wav.mean(0, keepdim=True), sr


def main() -> None:
    REF.mkdir(exist_ok=True)
    found = []
    step = TOTAL // POINTS
    for point in range(POINTS):
        offset = point * step + step // 2
        try:
            batch = rows(offset, PER_POINT)
        except Exception as exc:  # noqa: BLE001 - a point that fails is skipped
            print(f"offset {offset}: {exc}")
            continue
        pieces, rate, texts = [], None, []
        for r in batch:
            audio = r["row"]["audio"]
            src = audio[0]["src"] if isinstance(audio, list) and audio else None
            if not src:
                continue
            wav, sr = fetch(src)
            if rate is None:
                rate = sr
            if sr != rate:
                wav = torchaudio.functional.resample(wav, sr, rate)
            pieces += [wav, torch.zeros(1, int(0.3 * rate))]
            texts.append(r["row"]["text"])
        if not pieces:
            continue
        joined = torch.cat(pieces, dim=-1)
        name = f"indictts_{offset:06d}.wav"
        torchaudio.save(str(REF / name), joined, rate)
        seconds = joined.shape[-1] / rate
        found.append({"file": name, "offset": offset, "seconds": round(seconds, 1), "texts": texts})
        print(f"{name}: {seconds:.1f}s | {texts[0][:70]}")
        time.sleep(0.3)
    (REF / "indictts.json").write_text(json.dumps(found, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
