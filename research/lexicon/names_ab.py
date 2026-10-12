"""Which of the team's name respellings to keep, voice by voice (2026-10-12).

The listening-test round (2026-10-11) respelled 155 Indian names for English
letter rules, chosen by ear and applied in every voice. `names_check.py` on
twelve interviewer names, in all eight voices: recognisable (the name's
consonants heard right — vowels, where an accent lives, not judged) 79 of 96
respelled against 89 of 96 as written; a respelling broke 16 sayings and fixed
6. So the team's ear keeps a respelling in every voice except where it
measurably breaks the name and the name as written does not.

Two passes, M11 running with the lexicon to be heard, then a decision:

    python names_ab.py run plain        # M11 on the lexicon without the names
    python names_ab.py run respelled    # M11 on the team's lexicon
    python names_ab.py decide TEAM_LEXICON.json   # writes voices/lexicon.json

Each pass is saved after every sentence and picks up where it stopped.
"""

from __future__ import annotations

import difflib
import itertools
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
VOICES = HERE.parents[1] / "Backend" / "backend_M11_Voice_Engine" / "voices"
M11 = "http://127.0.0.1:8111"
WHO = {"X-Role": "student", "X-Candidate-Id": "4d0aa1c0-0000-4000-8000-000000000004"}
NAMES = HERE / "names_ab_names.json"


def post(path: str, data: bytes, content_type: str) -> bytes:
    request = urllib.request.Request(
        f"{M11}{path}", data=data, headers={**WHO, "Content-Type": content_type}
    )
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503) or attempt == 7:
                raise
            time.sleep(10 * (attempt + 1))  # the recogniser's minute
    raise RuntimeError("unreachable")


def skeleton(word: str) -> str:
    """The consonants, as an accent leaves them: vowels and h/y dropped,
    near-identical spellings merged, repeats collapsed."""
    w = word.lower()
    for a, b in (
        ("ph", "f"),
        ("th", "t"),
        ("dh", "d"),
        ("bh", "b"),
        ("kh", "k"),
        ("gh", "g"),
        ("sh", "s"),
        ("ch", "c"),
        ("q", "k"),
        ("c", "k"),
        ("w", "v"),
        ("z", "j"),
    ):
        w = w.replace(a, b)
    w = re.sub(r"[aeiouyh]", "", w)
    return re.sub(r"(.)\1+", r"\1", w)


def recognisable(name: str, heard: str) -> bool:
    tokens = re.findall(r"[a-z]+", heard.lower())
    candidates = tokens + [a + b for a, b in itertools.pairwise(tokens)]
    target = skeleton(name)
    best = max(
        (
            difflib.SequenceMatcher(None, target, skeleton(c)).ratio()
            for c in candidates
        ),
        default=0.0,
    )
    return best >= 0.99 or (len(target) >= 3 and best >= 0.8)


def run(condition: str) -> None:
    names = json.loads(NAMES.read_text(encoding="utf-8"))
    voices = sorted(
        set(
            json.loads((VOICES / "cast.json").read_text(encoding="utf-8"))[
                "cast"
            ].values()
        )
    )
    out = HERE / f"names_ab_{condition}.json"
    done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    for i in range(0, len(names), 3):
        group = names[i : i + 3]
        sentence = (
            f"I'm joined by {', '.join(group[:-1])} and {group[-1]}."
            if len(group) > 1
            else f"I'm joined by {group[0]}."
        )
        for voice in voices:
            key = f"{voice}|{sentence}"
            if key in done:
                continue
            wav = post(
                "/v1/voice/speak",
                json.dumps({"text": sentence, "voice": voice}).encode(),
                "application/json",
            )
            done[key] = {
                "names": group,
                "heard": json.loads(post("/v1/voice/transcribe", wav, "audio/wav"))[
                    "text"
                ],
            }
            out.write_text(json.dumps(done, indent=1), encoding="utf-8")
            print(
                f"{condition} {len(done)}/{len(voices) * ((len(names) + 2) // 3)} {voice} {done[key]['heard']}",
                flush=True,
            )


def verdicts(condition: str) -> dict[tuple[str, str], bool]:
    data = json.loads((HERE / f"names_ab_{condition}.json").read_text(encoding="utf-8"))
    return {
        (n, key.split("|", 1)[0]): recognisable(n, row["heard"])
        for key, row in data.items()
        for n in row["names"]
    }


def decide(team_lexicon: str) -> None:
    team = json.loads(pathlib.Path(team_lexicon).read_text(encoding="utf-8"))
    names = set(json.loads(NAMES.read_text(encoding="utf-8")))
    plain, said = verdicts("plain"), verdicts("respelled")
    voices = sorted({v for _, v in said})
    kept, dropped, broke = [], 0, 0
    for entry in team["entries"]:
        if entry["term"] not in names:
            kept.append(entry)
            continue
        broken = [
            v
            for v in voices
            if not said.get((entry["term"], v), True)
            and plain.get((entry["term"], v), False)
        ]
        broke += len(broken)
        good = [v for v in voices if v not in broken]
        if not good:
            dropped += 1
            continue
        if broken:
            entry = {
                **entry,
                "voices": good,
                "why": (entry.get("why") or "")
                + f" Not in {', '.join(broken)}: there the respelling was heard wrong and the name as written right (research/lexicon/names_ab.py).",
            }
        kept.append(entry)
    team["entries"] = kept
    (VOICES / "lexicon.json").write_text(
        json.dumps(team, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    p, s = sum(plain.values()), sum(said.values())
    print(
        f"recognisable: as written {p}/{len(plain)}, respelled {s}/{len(said)}; "
        f"{broke} name-voice pairs broken by a respelling; {dropped} names dropped whole"
    )


if __name__ == "__main__":
    if sys.argv[1] == "names":
        entries = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))[
            "entries"
        ]
        NAMES.write_text(
            json.dumps(
                [e["term"] for e in entries if "name" in (e.get("why") or "")], indent=1
            ),
            encoding="utf-8",
        )
        print(len(json.loads(NAMES.read_text(encoding="utf-8"))), "names")
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    elif sys.argv[1] == "decide":
        decide(sys.argv[2])
