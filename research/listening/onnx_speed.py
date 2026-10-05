"""Can Chatterbox Turbo speak live on a laptop CPU? The ONNX build, timed.

PyTorch on this i7-1260P makes ~7–9 speech tokens a second; real time needs
25 (the codec runs at 25 tokens per second of speech). ResembleAI's own ONNX
export (`ResembleAI/chatterbox-turbo-ONNX`, MIT) ships fp32, q8 and q4
language models and a one-step decoder. This runs the model card's loop —
greedy, as published — for each, on the same line and an IndicTTS voice, and
reports tokens a second and the real-time factor.

    <scratch venv>\\Scripts\\python onnx_speed.py [q4 q8 fp32]
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import librosa
import numpy as np
import onnxruntime
import soundfile as sf
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

HERE = pathlib.Path(__file__).resolve().parent
MODEL_ID = "ResembleAI/chatterbox-turbo-ONNX"
SAMPLE_RATE = 24000
START, STOP, SILENCE = 6561, 6562, 4299
NUM_KV_HEADS, HEAD_DIM = 16, 64
TEXT = "Okay, so. Say two keys land in the same bucket. How would a hash map deal with that? And, um, what does it cost you?"


def download(name: str, dtype: str) -> str:
    suffix = "" if dtype == "fp32" else "_quantized" if dtype == "q8" else f"_{dtype}"
    graph = hf_hub_download(MODEL_ID, subfolder="onnx", filename=f"{name}{suffix}.onnx")
    hf_hub_download(MODEL_ID, subfolder="onnx", filename=f"{name}{suffix}.onnx_data")
    return graph


def penalise(ids: np.ndarray, scores: np.ndarray, penalty: float = 1.2) -> np.ndarray:
    score = np.take_along_axis(scores, ids, axis=1)
    score = np.where(score < 0, score * penalty, score / penalty)
    out = scores.copy()
    np.put_along_axis(out, ids, score, axis=1)
    return out


def run(dtype: str, voice: pathlib.Path) -> dict:
    options = onnxruntime.SessionOptions()
    sessions = {
        name: onnxruntime.InferenceSession(download(name, dtype if name == "language_model" else "fp32"), options)
        for name in ("speech_encoder", "embed_tokens", "language_model", "conditional_decoder")
    }
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    audio, _ = librosa.load(voice, sr=SAMPLE_RATE)
    audio = audio[: SAMPLE_RATE * 15][np.newaxis, :].astype(np.float32)

    t0 = time.perf_counter()
    input_ids = tokenizer(TEXT, return_tensors="np")["input_ids"].astype(np.int64)
    tokens = np.array([[START]], dtype=np.int64)
    lm = sessions["language_model"]
    first_token_s = None
    for i in range(1024):
        embeds = sessions["embed_tokens"].run(None, {"input_ids": input_ids})[0]
        if i == 0:
            cond, prompt, spk_emb, spk_feat = sessions["speech_encoder"].run(None, {"audio_values": audio})
            embeds = np.concatenate((cond, embeds), axis=1)
            batch, seq, _ = embeds.shape
            past = {
                x.name: np.zeros([batch, NUM_KV_HEADS, 0, HEAD_DIM],
                                 dtype=np.float16 if x.type == "tensor(float16)" else np.float32)
                for x in lm.get_inputs() if "past_key_values" in x.name
            }
            mask = np.ones((batch, seq), dtype=np.int64)
            pos = np.arange(seq, dtype=np.int64).reshape(1, -1)
        logits, *present = lm.run(None, dict(inputs_embeds=embeds, attention_mask=mask, position_ids=pos, **past))
        next_logits = penalise(tokens, logits[:, -1, :])
        input_ids = np.argmax(next_logits, axis=-1, keepdims=True).astype(np.int64)
        tokens = np.concatenate((tokens, input_ids), axis=-1)
        if first_token_s is None:
            first_token_s = time.perf_counter() - t0
        if (input_ids.flatten() == STOP).all():
            break
        mask = np.concatenate([mask, np.ones((batch, 1), dtype=np.int64)], axis=1)
        pos = pos[:, -1:] + 1
        for j, key in enumerate(past):
            past[key] = present[j]
    lm_s = time.perf_counter() - t0

    speech = tokens[:, 1:-1]
    speech = np.concatenate([prompt, speech, np.full((1, 3), SILENCE, dtype=np.int64)], axis=1)
    t1 = time.perf_counter()
    wav = sessions["conditional_decoder"].run(None, dict(speech_tokens=speech, speaker_embeddings=spk_emb,
                                                          speaker_features=spk_feat))[0].squeeze(axis=0)
    decode_s = time.perf_counter() - t1
    seconds = len(wav) / SAMPLE_RATE
    name = f"onnx_turbo_{dtype}_{voice.stem}_question_spoken.wav"
    sf.write(HERE / name, wav, SAMPLE_RATE)
    n = tokens.shape[1] - 2
    total = lm_s + decode_s
    return {"dtype": dtype, "file": name, "tokens": n, "tokens_per_s": round(n / lm_s, 1),
            "first_token_s": round(first_token_s, 2), "lm_s": round(lm_s, 2), "decode_s": round(decode_s, 2),
            "audio_s": round(seconds, 2), "took_s": round(total, 2), "rtf": round(total / seconds, 2)}


def main() -> None:
    dtypes = sys.argv[1:] or ["q4", "q8", "fp32"]
    voices = json.loads((HERE / "reference" / "voices.json").read_text(encoding="utf-8"))
    voice = HERE / "reference" / next(v["file"] for v in voices if v["picked"])
    results = []
    for dtype in dtypes:
        r = run(dtype, voice)
        results.append(r)
        print(f"{dtype:5} {r['tokens_per_s']:5} tok/s  first token {r['first_token_s']}s  "
              f"{r['audio_s']}s of speech in {r['took_s']}s  -> RTF {r['rtf']}", flush=True)
    (HERE / "onnx_speed.json").write_text(json.dumps({"voice": voice.name, "results": results}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
