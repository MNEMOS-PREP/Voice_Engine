"""Build an interviewer's talking head from one portrait (M11 day 13, spec §15.6).

    .face_builder\\venv\\Scripts\\python scripts\\build_face.py PORTRAIT --persona ID

One image in, one avatar out. LAM (Large Avatar Model, Alibaba Tongyi Lab,
SIGGRAPH 2025) lifts the portrait into ~20,000 3D Gaussians bound to a FLAME
head, and the head goes into the rig the room's renderer animates: 51 ARKit
expressions, a jaw, eyes and a neck. Change the image and the whole person
changes; nothing else does.

It runs on a CPU. LAM's own pipeline needs CUDA in three places, and building
an avatar needs none of them:
  - The face fit (VHAP) rasterises only to draw debug images and a final colour
    check. LAM fits single images on landmarks alone (`photometric: false` in
    its config), so both are switched off.
  - The model's mesh subdivider is built on the GPU. Its CPU twin, which LAM
    ships alongside it, is used instead.
  - LAM renders a preview video with a CUDA Gaussian rasteriser. There is no
    preview here: the room's renderer is the preview.
It also needs Blender and the FBX SDK to write the rig. Here the rig is LAM's
own template with the new head's vertices written in. That is all LAM's
exporter changes (tools/generateARKITGLBWithBlender.py: only the base mesh's
vertices are replaced).

Licences: academic use only. LAM's weights are CC BY-NC 4.0, and FLAME 2023 is
under MPI's non-commercial licence. See the faces' ATTRIBUTION.md.

Setup, once: scripts/face_builder_setup.ps1.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import shutil
import struct
import sys
import time
import types
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / ".face_builder"
LAM = BUILDER / "LAM"
RIG = BUILDER / "rig"
FACES = ROOT / "Backend" / "backend_M11_Voice_Engine" / "faces"
WEIGHTS = LAM / "model_zoo" / "lam_models" / "releases" / "lam" / "lam-20k" / "step_045500"
TRACKING = LAM / "model_zoo" / "flame_tracking_models"

#: The renderer assigns clips to states by their order in animation.glb:
#: 0 is the idle loop (also listening and thinking), 1-6 are speaking.
CLIP_ORDER = (
    "yumi_h5_a3_idle",
    "yumi_h5_a3_speak_1",
    "yumi_h5_a3_speak_2",
    "yumi_h5_a3_speak_3",
    "yumi_h5_a3_speak_4",
    "yumi_h5_a3_speak",
    "yumi_h5_a3_speak_end",
)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


# ── running LAM's code on a CPU ──────────────────────────────────────────────


def prepare_lam() -> None:
    """Make LAM's modules importable on a machine with no CUDA."""
    # @torch.compile wraps two of LAM's forwards; there is no compiler here.
    os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
    # A CUDA Gaussian rasteriser is imported at module level and used only to
    # render previews.
    for name in ("diff_gaussian_rasterization_wda", "diff_gaussian_rasterization"):
        module = types.ModuleType(name)
        module.GaussianRasterizationSettings = None
        module.GaussianRasterizer = None
        sys.modules[name] = module
    # VHAP's renderer opens a CUDA rasteriser context in its constructor; its
    # projection maths, which the landmark fit uses, is plain torch.
    nvdiffrast = types.ModuleType("nvdiffrast")
    nvdiffrast_torch = types.ModuleType("nvdiffrast.torch")
    nvdiffrast_torch.RasterizeCudaContext = lambda *a, **k: None
    nvdiffrast_torch.RasterizeGLContext = lambda *a, **k: None
    nvdiffrast.torch = nvdiffrast_torch
    sys.modules["nvdiffrast"] = nvdiffrast
    sys.modules["nvdiffrast.torch"] = nvdiffrast_torch
    _shim_chumpy()
    # LAM's inference runner imports marching cubes (mesh export) and moviepy
    # (preview video) at module level. A Gaussian head uses neither.
    for name in ("mcubes", "moviepy", "moviepy.editor"):
        sys.modules.setdefault(name, types.ModuleType(name))
    # The landmark detector's metrics import scipy's `simps`, renamed
    # `simpson` in SciPy 1.14; the metrics are never run here.
    import scipy.integrate

    if not hasattr(scipy.integrate, "simps"):
        scipy.integrate.simps = scipy.integrate.simpson
    sys.path.insert(0, str(LAM))
    _shim_nms()
    _load_torchscript_as_torchscript()
    # VHAP's projection writes `.cuda()` into plain tensor maths
    # (render_nvdiffrast.world_to_clip). With no CUDA, the CPU tensor is it.
    import torch

    if not torch.cuda.is_available():
        torch.Tensor.cuda = lambda self, *args, **kwargs: self
        torch.nn.Module.cuda = lambda self, *args, **kwargs: self
    os.chdir(LAM)  # LAM and VHAP open their assets by relative path


def _load_torchscript_as_torchscript() -> None:
    """VGGHead's detector ships as a TorchScript archive and LAM opens it
    with `torch.load`, which PyTorch 2.6+ refuses for TorchScript. Such an
    archive is a graph, and `torch.jit.load` is its loader — not a pickle to
    be let through with `weights_only=False`."""
    import torch

    original = torch.load

    def load(f, *args, **kwargs):
        try:
            return original(f, *args, **kwargs)
        except RuntimeError as exc:
            if "TorchScript archives" not in str(exc):
                raise
            return torch.jit.load(f, map_location=kwargs.get("map_location"))

    torch.load = load


def _shim_nms() -> None:
    """FaceBoxes imports a Cython NMS that was never compiled here (its
    `cpu_nms.py` is an empty placeholder). Its own pure-numpy twin,
    `py_cpu_nms`, does the same job for the one face in a portrait."""
    import importlib.util

    # From its file, not its package: the package's __init__ is what
    # imports the missing module.
    path = LAM / "external" / "landmark_detection" / "FaceBoxesV2" / "utils" / "nms" / "py_cpu_nms.py"
    spec = importlib.util.spec_from_file_location("_faceboxes_py_cpu_nms", path)
    pure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pure)
    py_cpu_nms = pure.py_cpu_nms

    def cpu_soft_nms(dets, *args, **kwargs):  # never called on this path
        return py_cpu_nms(dets, kwargs.get("threshold", 0.3))

    module = types.ModuleType("external.landmark_detection.FaceBoxesV2.utils.nms.cpu_nms")
    module.cpu_nms = lambda dets, thresh: py_cpu_nms(dets, thresh)
    module.cpu_soft_nms = cpu_soft_nms
    sys.modules[module.__name__] = module


def _shim_chumpy() -> None:
    """FLAME's pickle names chumpy arrays; chumpy does not install on numpy 1.24+.

    Each pickled chumpy array keeps its values in `x`, which is all FLAME's
    loaders read (they call np.array on it).
    """
    try:
        import chumpy  # noqa: F401

        return
    except Exception:
        pass

    class _Array:
        def __init__(self, *args, **kwargs):
            pass

        def __setstate__(self, state):
            if isinstance(state, dict):
                self.__dict__.update(state)
            else:
                self.__dict__["_state"] = state

        def __array__(self, dtype=None, copy=None):
            value = self.__dict__.get("x", self.__dict__.get("a"))
            return np.asarray(value, dtype=dtype)

    class _Module(types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _Array

    for name in ("chumpy", "chumpy.ch", "chumpy.ch_ops", "chumpy.reordering", "chumpy.utils", "chumpy.logic"):
        sys.modules[name] = _Module(name)


# ── 1. the face fit: crop, matte, landmarks, FLAME ───────────────────────────


def fit_face(portrait: Path, work: Path) -> Path:
    """Fit FLAME to the portrait. Returns the export folder LAM reads."""
    import cv2
    import torch
    import torchvision
    import tyro
    import yaml

    from external.human_matting import StyleMatteEngine
    from external.landmark_detection.FaceBoxesV2.faceboxes_detector import FaceBoxesDetector
    from external.landmark_detection.infer_image import Alignment
    from external.vgghead_detector import VGGHeadDetector
    from tools.flame_tracking_single_image import expand_bbox
    from vhap.config.base import BaseTrackingConfig
    from vhap.export_as_nerf_dataset import NeRFDatasetWriter, TrackedFLAMEDatasetWriter, split_json
    from vhap.model.tracker import GlobalTracker

    name = "portrait"
    preprocess = work / "preprocess" / name
    for sub in ("images", "mask", "alpha_maps", "landmark2d"):
        (preprocess / sub).mkdir(parents=True, exist_ok=True)

    # The head, found and cropped as LAM does: its box widened 1.65x, 1024 px.
    log("finding the head")
    frame = torchvision.io.read_image(str(portrait))[:3, ...]
    heads = VGGHeadDetector(device="cpu", vggheadmodel_path=str(TRACKING / "vgghead" / "vgg_heads_l.trcd"))
    _, box, _ = heads(frame, 0)
    if box is None:
        raise SystemExit("No head found in the portrait. Use a front-facing head-and-shoulders photo.")
    box = expand_bbox(box, scale=1.65).long()
    crop = torchvision.transforms.functional.crop(
        frame, top=box[1], left=box[0], height=box[3] - box[1], width=box[2] - box[0]
    )
    crop = torchvision.transforms.functional.resize(crop, (1024, 1024), antialias=True)

    log("separating the head from the background")
    matting = StyleMatteEngine(device="cpu", human_matting_path=str(TRACKING / "matting" / "stylematte_synth.pt"))
    crop, mask = matting(crop / 255.0, return_type="matting", background_rgb=1.0)
    image = np.round((crop.cpu() * 255.0).permute(1, 2, 0).numpy()).astype(np.uint8)[:, :, (2, 1, 0)]
    cv2.imwrite(str(preprocess / "images" / "00000.png"), image)
    cv2.imwrite(str(preprocess / "mask" / "00000.png"), np.array(mask.cpu() * 255.0).astype(np.uint8))
    cv2.imwrite(str(preprocess / "alpha_maps" / "00000.jpg"), np.full_like(image, 255))

    log("placing 68 landmarks")
    faces = FaceBoxesDetector("FaceBoxes", str(TRACKING / "FaceBoxesV2.pth"), False, "cpu")
    args = argparse.Namespace(
        output_dir=str(work), config_name="alignment", model_path=str(TRACKING / "68_keypoints_model.pkl")
    )
    alignment = Alignment(args, str(TRACKING / "68_keypoints_model.pkl"), dl_framework="pytorch", device_ids=[-1])
    detections, _ = faces.detect(image, 0.8, 1)
    if not detections:
        raise SystemExit("No face found in the cropped head. Use a clear, front-facing photo.")
    x1, y1 = detections[0][2], detections[0][3]
    x2, y2 = x1 + detections[0][4], y1 + detections[0][5]
    scale = float(max(x2 - x1, y2 - y1) / 180)
    landmarks = alignment.analyze(image, scale, float((x1 + x2) / 2), float((y1 + y2) / 2))
    normalised = np.zeros((landmarks.shape[0], 3))
    normalised[:, :2] = landmarks / 1024
    np.savez(preprocess / "landmark2d" / "landmarks.npz", bounding_box=[], face_landmark_2d=normalised[None, ...])

    log("fitting FLAME to the landmarks (650 steps)")
    text = yaml.safe_load((LAM / "configs" / "vhap_tracking" / "base_tracking_config.yaml").read_text())
    # The YAML names a PosixPath, which Windows cannot build.
    config = tyro.from_yaml(BaseTrackingConfig, text.replace("pathlib.PosixPath", "pathlib.Path"))
    config.data.sequence = name
    config.data.root_folder = work / "preprocess"
    config.exp.output_folder = work / "tracking"
    config.device = "cpu"
    config.log.interval_media = 10**9  # debug images need the rasteriser
    tracker = GlobalTracker(config)
    # The final evaluation scores colour with the rasteriser; only its first
    # act, saving the fitted parameters, is needed.
    tracker.evaluate = lambda make_visualization=True, epoch=0: tracker.save_result(epoch=epoch)
    tracker.optimize()

    log("writing the fit")
    runs = sorted((work / "tracking").iterdir())
    source = runs[-1]
    config_data = yaml.load((source / "config.yml").read_text(), Loader=yaml.Loader)
    export = work / "export" / name
    NeRFDatasetWriter(config_data.data, export, None, None, "white").write()
    TrackedFLAMEDatasetWriter(config_data.model, source, export, mode="param", epoch=-1).write()
    split_json(export)
    torch.set_grad_enabled(True)
    return export


# ── 2. one image to 3D Gaussians ─────────────────────────────────────────────


def lift(export: Path):
    """LAM's forward pass: the portrait to Gaussians on the shaped FLAME head."""
    import torch
    from einops import rearrange
    from omegaconf import OmegaConf
    from safetensors.torch import load_file

    import lam.models.encoders.dinov2_fusion_wrapper as dinov2_wrapper
    import lam.models.rendering.flame_model.flame as lam_flame
    from lam.models import ModelLAM
    from lam.runners.infer.head_utils import preprocess_image

    # The subdivider's CPU twin; and no DINOv2 download, since LAM's checkpoint
    # carries the encoder's trained weights.
    lam_flame.FlameHeadSubdivided.get_subdivider = lam_flame.FlameHeadSubdivided.get_subdivider_cpu
    build = dinov2_wrapper.Dinov2FusionWrapper._build_dinov2
    dinov2_wrapper.Dinov2FusionWrapper._build_dinov2 = staticmethod(
        lambda model_name, modulation_dim=None, pretrained=True: build(model_name, modulation_dim, pretrained=False)
    )

    log("loading LAM-20K")
    config = OmegaConf.load(LAM / "configs" / "inference" / "lam-20k-8gpu.yaml")
    model = ModelLAM(**config.model)
    state = model.state_dict()
    loaded = 0
    for key, value in load_file(str(WEIGHTS / "model.safetensors"), device="cpu").items():
        if key in state and state[key].shape == value.shape:
            state[key].copy_(value)
            loaded += 1
    if loaded < len(state) * 0.95:
        raise SystemExit(f"LAM's checkpoint filled only {loaded} of {len(state)} tensors.")
    model.eval()

    image, _, _, shape = preprocess_image(
        str(export / "images" / "00000_00.png"),
        mask_path=str(export / "fg_masks" / "00000_00.png"),
        intr=None,
        pad_ratio=0,
        bg_color=1.0,
        max_tgt_size=None,
        aspect_standard=1.0,
        enlarge_ratio=[1.0, 1.0],
        render_tgt_size=config.dataset.source_image_res,
        multiply=14,
        need_mask=True,
        get_shape_param=True,
    )

    log("lifting the portrait to Gaussians")
    with torch.no_grad():
        flame = {"betas": shape.unsqueeze(0)}
        points, _ = model.renderer.get_query_points(flame, device=torch.device("cpu"))
        latent, feats = model.forward_latent_points(image, camera=None, query_points=points)
        feats_bchw = rearrange(feats, "b (h w) c -> b c h w", h=int(math.sqrt(feats.shape[1])))
        gaussians, _, _, _ = model.renderer.forward_gs(
            gs_hidden_features=latent,
            query_points=points,
            flame_data=flame,
            additional_features={"image_feats": feats, "image": image, "image_feats_bchw": feats_bchw},
        )
    return gaussians[0], points[0].numpy().astype(np.float64), model.renderer.flame_model


# ── 3. the rig: LAM's template, the new head's vertices ──────────────────────

_JSON, _BIN = 0x4E4F534A, 0x004E4942


def read_glb(data: bytes) -> tuple[dict, bytearray]:
    magic, _, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError("not a GLB file")
    offset, gltf, binary = 12, None, bytearray()
    while offset < length:
        size, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8 : offset + 8 + size]
        if kind == _JSON:
            gltf = json.loads(chunk)
        elif kind == _BIN:
            binary = bytearray(chunk)
        offset += 8 + size
    return gltf, binary


def write_glb(gltf: dict, binary: bytes) -> bytes:
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary = bytes(binary) + b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(text), _JSON) + text + struct.pack("<II", len(binary), _BIN) + binary
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def _head_positions(gltf: dict, binary: bytes) -> tuple[dict, int, np.ndarray]:
    primitive = gltf["meshes"][0]["primitives"][0]
    accessor = gltf["accessors"][primitive["attributes"]["POSITION"]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", 12)
    if stride != 12 or accessor["componentType"] != 5126:
        raise ValueError("the rig's positions are not packed float32 triples")
    count = accessor["count"]
    positions = np.frombuffer(bytes(binary[start : start + 12 * count]), dtype="<f4").reshape(count, 3)
    return accessor, start, positions.astype(np.float64)


def similarity(source: np.ndarray, target: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, float]:
    """Scale, rotation and shift taking source to target (Umeyama); and the worst miss."""
    mu_s, mu_t = source.mean(0), target.mean(0)
    s, t = source - mu_s, target - mu_t
    u, d, vt = np.linalg.svd(t.T @ s / len(source))
    sign = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign[2, 2] = -1
    rotation = u @ sign @ vt
    scale = float(np.trace(np.diag(d) @ sign) / s.var(0).sum())
    shift = mu_t - scale * rotation @ mu_s
    miss = float(np.abs(source @ (scale * rotation).T + shift - target).max())
    return scale, rotation, shift, miss


def fbx_head_placement() -> tuple[float, np.ndarray]:
    """`(scale, shift)` taking FLAME's metres into the rig's space, read from
    the template FBX's `head_final` model: its Lcl Scaling and Lcl
    Translation, in centimetres (the file's UnitScaleFactor is 1)."""
    text = (RIG / "template_file.fbx").read_text(encoding="utf-8", errors="replace")
    start = text.index('"Model::head_final", "Mesh"')
    block = text[start : text.index("Culling", start)]

    def triple(name: str) -> np.ndarray:
        line = next(row for row in block.splitlines() if f'P: "{name}"' in row)
        return np.array([float(value) for value in line.split(",")[-3:]])

    scaling = triple("Lcl Scaling")
    if np.ptp(scaling) > 1e-6:
        raise SystemExit("The template's head is scaled unevenly; the rig is not LAM's.")
    return float(scaling[0]) / 100.0, triple("Lcl Translation") / 100.0


def rig_with(head: np.ndarray, template: np.ndarray) -> tuple[bytes, list[int]]:
    """skin.glb: the template rig, its base mesh replaced by this head."""
    gltf, binary = read_glb((RIG / "skin.glb").read_bytes())
    accessor, start, rig_positions = _head_positions(gltf, binary)
    if len(rig_positions) != len(head):
        raise SystemExit(f"The rig has {len(rig_positions)} vertices and LAM's head {len(head)}.")
    # Where FLAME's metres go in the rig: LAM's template FBX says it exactly
    # (the head mesh's own translation and scale, in a centimetre file), and
    # LAM's exporter writes the head's vertices into that FBX unchanged.
    scale, shift = fbx_head_placement()
    # A sanity check that this IS LAM's rig, from the rig's own base mesh. The
    # base is whoever the rig was exported for (the template is shipped only
    # as FBX), so it fits the template to a few millimetres, not exactly.
    fit_scale, rotation, fit_shift, miss = similarity(template, rig_positions)
    log(
        f"rig: exact scale {scale:.4f} shift {np.round(shift, 4).tolist()}; "
        f"fitted {fit_scale:.4f} {np.round(fit_shift, 4).tolist()}, worst miss {miss * 1000:.1f} mm"
    )
    if (
        abs(fit_scale - scale) > 0.02
        or np.abs(fit_shift - shift).max() > 0.01
        or np.abs(rotation - np.eye(3)).max() > 0.02
        or miss > 0.02
    ):
        raise SystemExit("skin.glb is not LAM's head rig (its base mesh is far from the template).")
    placed = head * scale + shift
    binary[start : start + 12 * len(placed)] = placed.astype("<f4").tobytes()
    accessor["min"] = placed.min(0).tolist()
    accessor["max"] = placed.max(0).tolist()
    # LAM's vertex order: by height, as its Blender script sorts them.
    order = np.argsort(placed[:, 1], kind="stable").tolist()
    return write_glb(gltf, binary), order


def animation() -> bytes:
    """animation.glb with its clips in the order the renderer assigns them."""
    gltf, binary = read_glb((RIG / "animation.glb").read_bytes())
    clips = {clip.get("name"): clip for clip in gltf["animations"]}
    missing = [name for name in CLIP_ORDER if name not in clips]
    if missing:
        raise SystemExit(f"animation.glb has no {', '.join(missing)}")
    gltf["animations"] = [clips[name] for name in CLIP_ORDER]
    return write_glb(gltf, binary)


def ply_bytes(gaussians) -> bytes:
    """offset.ply as LAM writes it: offsets from the head's vertices, RGB colour."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "offset.ply"
        gaussians.save_ply(str(path), rgb2sh=False, offset2xyz=True)
        return path.read_bytes()


def pack(persona: str, files: dict[str, bytes], meta: dict) -> Path:
    """<persona>.zip: one folder, as the renderer expects."""
    FACES.mkdir(parents=True, exist_ok=True)
    target = FACES / f"{persona}.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(zipfile.ZipInfo(f"{persona}/"), b"")
        for name, data in files.items():
            archive.writestr(f"{persona}/{name}", data)
        archive.writestr(f"{persona}/meta.json", json.dumps(meta, indent=2))
    target.write_bytes(buffer.getvalue())
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("portrait", type=Path, help="a front-facing head-and-shoulders portrait")
    parser.add_argument("--persona", required=True, help="the M06 persona id the face is for")
    parser.add_argument("--keep", action="store_true", help="keep the work folder (the fit, the crop)")
    args = parser.parse_args()

    portrait = args.portrait.resolve()
    if not portrait.exists():
        raise SystemExit(f"No such portrait: {portrait}")
    for need in (WEIGHTS / "model.safetensors", TRACKING / "FaceBoxesV2.pth", RIG / "skin.glb", RIG / "animation.glb"):
        if not need.exists():
            raise SystemExit(f"Missing {need}. Run scripts/face_builder_setup.ps1 first.")

    started = time.time()
    work = BUILDER / "work" / args.persona
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    # torchvision reads PNG and JPEG; any portrait becomes a PNG first.
    from PIL import Image

    source = work / "portrait.png"
    with Image.open(portrait) as image:
        image.convert("RGB").save(source)

    prepare_lam()
    export = fit_face(source, work)
    gaussians, head, flame = lift(export)
    template = flame.v_template_up.cpu().numpy().astype(np.float64)
    skin, order = rig_with(head, template)
    files = {
        "offset.ply": ply_bytes(gaussians),
        "skin.glb": skin,
        "animation.glb": animation(),
        "vertex_order.json": json.dumps(order).encode(),
    }
    meta = {
        "persona": args.persona,
        "portrait": portrait.name,
        "built": time.strftime("%Y-%m-%d"),
        "gaussians": int(gaussians.xyz.shape[0]),
        "made_with": "LAM-20K (3DAIGC, CC BY-NC 4.0) on FLAME 2023 (MPI, non-commercial); build_face.py",
        "ai_generated": True,
    }
    target = pack(args.persona, files, meta)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    log(f"{target.name}: {target.stat().st_size / 1e6:.1f} MB in {time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
