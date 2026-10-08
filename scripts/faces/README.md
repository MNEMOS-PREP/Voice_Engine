# Making the interviewers' faces

`make_faces.py` makes every interviewer's head, one at a time, resuming where
it stopped:

1. a portrait from the persona's written description (`portraits.json`), with
   FLUX.1-schnell run by stable-diffusion.cpp;
2. a 3D head from that portrait, with LAM (`build_face.py`).

Heads land in `Backend/backend_M11_Voice_Engine/faces/<persona>.zip`. M11
serves them, and the interview room shows a drawn face for anyone who has no
head yet. **The faces are optional.** Without them, every interviewer has the
drawn face.

On a laptop with Intel Iris Xe graphics, one head takes about 8 minutes
(4 for the portrait, 3.5 for the head), so all 39 take about five hours. The
builder runs at below-normal priority, so the machine stays usable.

**Academic use only.** LAM's weights are CC BY-NC 4.0 and FLAME 2023 is
non-commercial. See `Backend/backend_M11_Voice_Engine/faces/ATTRIBUTION.md`.

**Quicker:** the heads are plain files. If a teammate has built them, copy
their `faces\*.zip` into the same folder on your machine and restart M11.

## Setup, once (~15 GB of downloads)

Everything lives in `Voice_Engine\.face_builder\` (gitignored). The commands
below are for the Windows Command Prompt, run from `Voice_Engine`.

**1. Python 3.11 and the packages** (CPU only; no CUDA is needed):

```bat
py -3.11 -m venv .face_builder\venv
.face_builder\venv\Scripts\python -m pip install -r scripts\faces\builder-requirements.txt
```

**2. LAM's code, at the commit the builder was written against:**

```bat
git clone https://github.com/aigc3d/LAM.git .face_builder\LAM
git -C .face_builder\LAM checkout 339573649dd93df4cba8093a964e85a80d1b61f3
```

`build_face.py` patches LAM's CUDA-only parts in memory as it runs. Do not
edit the checkout.

**3. LAM's models**, into `.face_builder\downloads\`, then unpacked inside
`.face_builder\LAM\`, as LAM's own README does:

| File | From |
|---|---|
| `LAM_assets.tar` | <https://huggingface.co/3DAIGC/LAM-assets/resolve/main/LAM_assets.tar> |
| `thirdparty_models.tar` | <https://huggingface.co/3DAIGC/LAM-assets/resolve/main/thirdparty_models.tar> |
| `model.safetensors` (2.4 GB) | <https://huggingface.co/3DAIGC/LAM-20K/resolve/main/model.safetensors> |

```bat
cd .face_builder\LAM
tar -xf ..\downloads\LAM_assets.tar
tar -xf ..\downloads\thirdparty_models.tar
mkdir model_zoo\lam_models\releases\lam\lam-20k\step_045500
copy ..\downloads\model.safetensors model_zoo\lam_models\releases\lam\lam-20k\step_045500\
cd ..\..
```

**4. The rig** the room's renderer animates, into `.face_builder\rig\`:

| File | From |
|---|---|
| `skin.glb`, `animation.glb`, `iris_occlusion.json` | `Jack.zip` from gsplat-talkinghead (MIT): <https://raw.githubusercontent.com/NavodPeiris/gsplat-talkinghead/HEAD/gsplat-talkinghead/assets/Jack.zip> |
| `template_file.fbx` | `sample_oac.tar`, LAM's OpenAvatarChat sample: <https://virutalbuy-public.oss-cn-hangzhou.aliyuncs.com/share/aigc3d/data/LAM/sample_oac.tar> |

`build_face.py` checks that this is LAM's rig before it writes a head.

**5. The portrait model**, into `.face_builder\flux\`. Unzip the two
stable-diffusion.cpp builds into `sd-vulkan\` and `sd-cpu\`. The Vulkan
build uses the integrated GPU; the CPU build is the fallback.

| File | From |
|---|---|
| `sd-vulkan.zip` | <https://github.com/leejet/stable-diffusion.cpp/releases/download/master-945-a1ded76/sd-master-a1ded76-bin-win-vulkan-x64.zip> |
| `sd-cpu.zip` | <https://github.com/leejet/stable-diffusion.cpp/releases/download/master-945-a1ded76/sd-master-a1ded76-bin-win-cpu-x64.zip> |
| `flux1-schnell-Q4_K_S.gguf` (6.8 GB) | <https://huggingface.co/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q4_K_S.gguf> |
| `t5xxl-Q4_K_M.gguf` (2.9 GB) | <https://huggingface.co/city96/t5-v1_1-xxl-encoder-gguf/resolve/main/t5-v1_1-xxl-encoder-Q4_K_M.gguf> |
| `clip_l.safetensors` | <https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors> |
| `ae.safetensors` | <https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors> |

The lip-sync model (wav2arkit, 400 MB) is not part of this. M11 downloads it
the first time it makes a face.

## Run

```bat
.face_builder\venv\Scripts\python scripts\make_faces.py
```

- `--only os_suresh dsa_rohit` makes just those heads.
- `--portraits-only` makes the portraits and stops.
- Progress is in `.face_builder\make_faces.log`.
- A portrait or head that already exists is kept. Delete one to make it
  again; the same prompt and seed make the same face.
