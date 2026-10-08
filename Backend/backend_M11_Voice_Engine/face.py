"""The interviewer's face, moving with their own voice (M11 day 13, 2026-10-08).

Lip sync is computed from the audio the interviewer actually says, never from
the text: wav2arkit (myned-ai/wav2arkit_cpu, Apache-2.0 — wav2vec2-base and
LAM's audio-to-expression decoder) turns a sentence's waveform into the 52
ARKit blendshapes at 30 frames a second. They are the same 52 the head's rig
is built with (`scripts/build_face.py`), so the browser hands each frame
straight to the renderer at the audio's current time. On this laptop's CPU a
4.6-second sentence takes 0.3 s: frames are made when the sentence is made,
and are ready before the browser asks.

Frames are keyed like the sentence's audio (`tts.Engine.cache_key`), so a
sentence said again — from the cache — moves the face the same way, and the
browser asks for them by the key its audio came with (`X-Face`).

The heads themselves (`faces/<persona>.zip`) are built offline, one portrait
each, by `scripts/make_faces.py`. Every portrait is AI-generated and labelled
so (spec §15.6); `meta.json` in each zip says how it was made.
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import wave
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
FACES_DIR = Path(os.getenv("M11_FACES_DIR") or HERE / "faces")
MODEL_ID = "myned-ai/wav2arkit_cpu"
MODEL_FILES = ("wav2arkit_cpu.onnx", "wav2arkit_cpu.onnx.data")
#: Where the face builder already downloaded the model, so it is not fetched
#: twice on a machine that builds faces.
BUILDER_DOWNLOADS = HERE.parents[1] / ".face_builder" / "downloads"
FPS = 30
MODEL_RATE = 16_000

#: What a face seen small needs and a face seen close does not: the mouth's
#: opening, a little emphasised. wav2arkit's values are natural speech (the
#: jaw opens to about 0.2), which on a 300-pixel tile reads as a face barely
#: moving. Only the channels that open and round the mouth; nothing else.
EMPHASIS: dict[str, float] = {
    "jawOpen": 1.6,
    "mouthLowerDownLeft": 1.3,
    "mouthLowerDownRight": 1.3,
    "mouthUpperUpLeft": 1.3,
    "mouthUpperUpRight": 1.3,
    "mouthFunnel": 1.5,
    "mouthPucker": 1.4,
}

#: Frames kept in memory; the rest are on disk beside the audio.
MEMORY = 256


class FaceUnavailable(RuntimeError):
    """The lip-sync model cannot be loaded here."""


def _model_dir() -> Path:
    """Where the model's two files are: an override, the face builder's copy,
    or Hugging Face's cache (downloaded on first use, 400 MB)."""
    override = os.getenv("M11_FACE_MODEL_DIR")
    for folder in (Path(override) if override else None, BUILDER_DOWNLOADS):
        if folder and all((folder / name).exists() for name in MODEL_FILES):
            return folder
    try:
        from huggingface_hub import hf_hub_download

        paths = [hf_hub_download(MODEL_ID, name) for name in (*MODEL_FILES, "config.json")]
    except Exception as exc:  # noqa: BLE001 - any failure means no face
        raise FaceUnavailable(f"the lip-sync model could not be fetched: {exc}") from None
    return Path(paths[0]).parent


def _names(folder: Path) -> list[str]:
    for name in ("config.json", "wav2arkit_config.json"):
        path = folder / name
        if path.exists():
            return list(json.loads(path.read_text(encoding="utf-8"))["blendshape_names"])
    raise FaceUnavailable("the lip-sync model has no config naming its blendshapes")


def read_wav(data: bytes) -> tuple[Any, int]:
    """Mono float samples and their rate, from a 16-bit PCM WAV."""
    import numpy as np

    with wave.open(io.BytesIO(data)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("expected 16-bit PCM audio")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def resample(samples: Any, rate: int, to: int = MODEL_RATE) -> Any:
    """Linear resampling — enough for a model that listens for phonemes."""
    import numpy as np

    if rate == to or len(samples) == 0:
        return samples.astype(np.float32)
    positions = np.arange(0, len(samples), rate / to)
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)


def shape(raw: Any, names: list[str]) -> Any:
    """The model's frames as the face shows them: the mouth emphasised, a
    light 1-2-1 smoothing over time (it steadies jitter without losing a
    closure: a /p/ is several frames long), and every value in [0, 1]."""
    import numpy as np

    frames = np.asarray(raw, dtype=np.float32).copy()
    for name, gain in EMPHASIS.items():
        if name in names:
            frames[:, names.index(name)] *= gain
    if len(frames) >= 3:
        padded = np.concatenate([frames[:1], frames, frames[-1:]])
        frames = 0.25 * padded[:-2] + 0.5 * padded[1:-1] + 0.25 * padded[2:]
    return np.clip(frames, 0.0, 1.0)


class FaceEngine:
    """The lip-sync model, loaded once, and the frames it has made."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._session: Any = None
        self._names: list[str] = []
        self._load_lock = threading.Lock()
        self._memory: OrderedDict[str, dict] = OrderedDict()
        self._memory_lock = threading.Lock()
        self._cache_dir = cache_dir
        # One worker: frames are made after the sentence, never instead of it.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="m11-face")
        self.error: str | None = None

    # ── the model ────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._session is not None:
            return
        with self._load_lock:
            if self._session is not None:
                return
            if os.getenv("M11_FACE") == "off":
                raise FaceUnavailable("lip sync is switched off (M11_FACE=off)")
            try:
                import onnxruntime as ort

                folder = _model_dir()
                options = ort.SessionOptions()
                # Two threads: the voice is the bottleneck, not the face.
                options.intra_op_num_threads = 2
                self._names = _names(folder)
                self._session = ort.InferenceSession(
                    str(folder / MODEL_FILES[0]), options, providers=["CPUExecutionProvider"]
                )
            except FaceUnavailable as exc:
                self.error = str(exc)
                raise
            except Exception as exc:  # noqa: BLE001
                self.error = f"the lip-sync model did not load: {exc}"
                raise FaceUnavailable(self.error) from None

    def infer(self, samples: Any) -> Any:
        """Raw model frames for 16 kHz mono samples."""
        self._load()
        out = self._session.run(None, {"audio_waveform": samples[None, :]})[0]
        return out[0]

    # ── frames ───────────────────────────────────────────────────────────

    def frames_for(self, audio: bytes) -> dict:
        """`{fps, names, frames}` for one sentence's WAV."""
        samples, rate = read_wav(audio)
        raw = self.infer(resample(samples, rate))
        shaped = shape(raw, self._names)
        return {
            "fps": FPS,
            "names": list(self._names),
            "frames": [[round(float(v), 3) for v in row] for row in shaped],
        }

    def _path(self, key: str) -> Path | None:
        from . import tts

        folder = self._cache_dir or tts.CACHE_DIR / "face"
        return folder / f"{key}.json"

    def _remember(self, key: str, frames: dict) -> None:
        with self._memory_lock:
            self._memory[key] = frames
            self._memory.move_to_end(key)
            while len(self._memory) > MEMORY:
                self._memory.popitem(last=False)

    def cached(self, key: str) -> dict | None:
        with self._memory_lock:
            if key in self._memory:
                self._memory.move_to_end(key)
                return self._memory[key]
        path = self._path(key)
        if path is not None and path.exists():
            frames = json.loads(path.read_text(encoding="utf-8"))
            self._remember(key, frames)
            return frames
        return None

    def make(self, key: str, audio: bytes) -> dict:
        """The frames for this sentence, made now unless already made."""
        hit = self.cached(key)
        if hit is not None:
            return hit
        frames = self.frames_for(audio)
        self._remember(key, frames)
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(frames, separators=(",", ":")), encoding="utf-8")
        except OSError as exc:
            log.info("M11 face frames not written: %s", exc)
        return frames

    def prepare(self, key: str, audio: bytes) -> None:
        """Start making a sentence's frames, off the request that made it."""

        def work() -> None:
            try:
                self.make(key, audio)
            except FaceUnavailable:
                pass
            except Exception:  # noqa: BLE001 - a face is never worth a crash
                log.exception("M11 face frames failed for %s", key)

        if self.error is None:
            self._pool.submit(work)


# ── the heads ────────────────────────────────────────────────────────────


def head_path(persona: str) -> Path | None:
    path = FACES_DIR / f"{persona}.zip"
    return path if path.exists() else None


def heads() -> list[dict]:
    """Every built head, with what its zip says about itself."""
    import zipfile

    out = []
    for path in sorted(FACES_DIR.glob("*.zip")):
        meta: dict = {}
        try:
            with zipfile.ZipFile(path) as archive:
                inside = next((n for n in archive.namelist() if n.endswith("meta.json")), None)
                if inside:
                    meta = json.loads(archive.read(inside).decode("utf-8"))
        except (zipfile.BadZipFile, ValueError, KeyError):
            continue
        out.append(
            {
                "persona": path.stem,
                "bytes": path.stat().st_size,
                "built": meta.get("built"),
                "gaussians": meta.get("gaussians"),
                "made_with": meta.get("made_with"),
                "ai_generated": bool(meta.get("ai_generated", True)),
            }
        )
    return out


_engine: FaceEngine | None = None


def engine() -> FaceEngine:
    global _engine
    if _engine is None:
        _engine = FaceEngine()
    return _engine


def set_engine(value: FaceEngine | None) -> None:
    """Tests install a fake; None goes back to the real one."""
    global _engine
    _engine = value


__all__ = [
    "EMPHASIS",
    "FPS",
    "FaceEngine",
    "FaceUnavailable",
    "engine",
    "head_path",
    "heads",
    "read_wav",
    "resample",
    "set_engine",
    "shape",
]
