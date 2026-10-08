# The interviewers' faces — what made them, and on what terms

Every head in this folder (`<persona>.zip`, built by `scripts/make_faces.py`,
not committed) is **AI-generated**. Each portrait was made from a written
description (`scripts/faces/portraits.json`: the prompt and the seed). None is
a photograph of a real person, and none was made to resemble one. In the
interview room every head carries an **"AI"** label (spec §15.6).

**Academic use only.** LAM's weights are CC BY-NC 4.0 and FLAME 2023 is under
MPI's non-commercial licence, so these heads may not be used commercially. A
commercial deployment needs another way to make them.

Each head's own `meta.json` repeats this: the persona, the date it was built,
`"ai_generated": true`, and what it was made with.

## The portrait

| What | Made by | Licence |
|---|---|---|
| FLUX.1-schnell — the image model | Black Forest Labs | Apache-2.0 |
| Its GGUF quantisation (`flux1-schnell-Q4_K_S.gguf`) | city96 | Apache-2.0 |
| T5-v1.1-XXL text encoder, GGUF (`t5xxl-Q4_K_M.gguf`) | Google; quantised by city96 | Apache-2.0 |
| CLIP ViT-L/14 text encoder (`clip_l.safetensors`) | OpenAI; packaged by comfyanonymous | MIT |
| FLUX's autoencoder (`ae.safetensors`) | Black Forest Labs; copy from Comfy-Org's Lumina Image 2.0 repackaging | Apache-2.0 |
| stable-diffusion.cpp, which runs them | leejet and contributors | MIT |

## The head

| What | Made by | Licence |
|---|---|---|
| LAM — one image to a 3D Gaussian head (code) | Alibaba Tongyi Lab, 3DAIGC (SIGGRAPH 2025) | Apache-2.0 |
| LAM-20K weights | 3DAIGC | **CC BY-NC 4.0** |
| FLAME 2023 head model and the face-tracking models (LAM's `thirdparty_models`) | Max Planck Institute for Intelligent Systems, and the models' authors | **MPI non-commercial** |
| The rig's template (`template_file.fbx`) | LAM's OpenAvatarChat sample (`sample_oac`) | from LAM's authors |
| The rig (`skin.glb`, `animation.glb`, `iris_occlusion.json`) | gsplat-talkinghead (NavodPeiris), its sample `Jack.zip` | MIT |

## In the browser

| What | Made by | Licence |
|---|---|---|
| gsplat-flame-avatar-renderer, which draws each head | myned-ai | MIT |
| wav2arkit_cpu, which makes the lip sync from the voice's audio (M11 `face.py`) | myned-ai; wav2vec2-base (Meta) and LAM's audio-to-expression decoder | Apache-2.0 |

The voices are credited separately, in `../voices/ATTRIBUTION.md`.
