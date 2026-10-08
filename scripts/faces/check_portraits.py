"""Check portraits the way `build_face.py` will, without building heads.

    .face_builder\\venv\\Scripts\\python scripts\\faces\\check_portraits.py PORTRAIT_OR_FOLDER ...

For each portrait: mouth closed, both eyes open, facing the camera, level
(`build_face.portrait_check`). Prints one line each and writes
`.face_builder/work/checks.json`. Used to calibrate `build_face.CHECK`
(2026-10-09) on the team's Avatar_Lab portraits and the first cast.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import build_face


def portraits(arguments: list[str]) -> list[Path]:
    found: list[Path] = []
    for argument in arguments:
        path = Path(argument).resolve()
        if path.is_dir():
            found += sorted(
                p
                for p in path.iterdir()
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
            )
        else:
            found.append(path)
    return found


def main() -> None:
    from PIL import Image

    wanted = portraits(sys.argv[1:])
    build_face.prepare_lam()
    results = {}
    for portrait in wanted:
        work = build_face.BUILDER / "work" / f"check_{portrait.stem}"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        source = work / "portrait.png"
        with Image.open(portrait) as image:
            image.convert("RGB").save(source)
        try:
            build_face.fit_face(source, work, check_only=True)
            verdict = json.loads((work / "check.json").read_text(encoding="utf-8"))
        except SystemExit as exc:
            verdict = {"ok": False, "reasons": [f"no face found ({exc.code})"]}
        results[str(portrait)] = verdict
        print(
            f"{'ok  ' if verdict['ok'] else 'FAIL'} {portrait.parent.name}/{portrait.name}: {json.dumps(verdict)}",
            flush=True,
        )
        shutil.rmtree(work, ignore_errors=True)
    out = build_face.BUILDER / "work" / "checks.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
