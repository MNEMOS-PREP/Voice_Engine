"""Builds listen.html — every candidate voice, the same lines, side by side.

Reads whichever manifests exist (chatterbox.json, chatterbox_clone.json,
samples.json from Orpheus, gemini.json) and embeds them, so the page opens
from disk with no server. Today's voice is played live by the browser's own
speech synthesis — open the page in Microsoft Edge to hear the Neerja voice
students hear now.

Blind mode shuffles each line's clips and hides their names: the arena's
method (Artificial Analysis), for a team or student panel to vote "which
sounds most like a person?" before anyone knows which is which.

    python build_page.py
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

LINE_LABEL = {
    "greeting": "The greeting",
    "question": "A technical question",
    "followup": "A follow-up, reacting to the answer",
}
SOURCE_LABEL = {
    "chatterbox_turbo": "Chatterbox Turbo · built-in voice (free, offline, MIT)",
    "chatterbox_clone_dailytalk0": "Chatterbox Turbo · cloned from DailyTalk speaker 0 (conversational data)",
    "chatterbox_clone_dailytalk1": "Chatterbox Turbo · cloned from DailyTalk speaker 1 (conversational data)",
    "orpheus_hannah": "Orpheus on Groq · hannah",
    "orpheus_daniel": "Orpheus on Groq · daniel",
    "gemini": "Gemini 3.8 Flash TTS",
}


def load(name: str) -> list[dict]:
    path = HERE / name
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [c for c in data.get("clips", []) if (HERE / c["file"]).exists()]


def source_of(clip: dict) -> str:
    stem = clip["file"].removesuffix(".wav")
    if clip.get("label") and stem.endswith("_" + clip["line"]):
        return stem[: -len(clip["line"]) - 1]  # one voice, across its lines
    for key in sorted(SOURCE_LABEL, key=len, reverse=True):
        if stem.startswith(key):
            return key
    return stem.split("_")[0]


def accent_of(clip: dict) -> str:
    """The roster wants mostly Indian voices and some foreign ones."""
    return "indian" if "indictts" in clip["file"] else "foreign"


def onnx_clips() -> list[dict]:
    """The fast ONNX build's clips, so its quality can be heard, not assumed."""
    path = HERE / "onnx_speed.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        {**r, "line": "question_spoken", "text": "Okay, so. Say two keys land in the same bucket. How would a hash map deal with that? And, um, what does it cost you?",
         "label": f"Chatterbox Turbo, ONNX build ({r['dtype']}) · same Indian voice as voice 1 · {r['tokens_per_s']} tokens/s"}
        for r in data["results"] if (HERE / r["file"]).exists()
    ]


def main() -> None:
    clips = (
        load("chatterbox.json") + load("chatterbox_clone.json") + load("indian_clones.json")
        + onnx_clips() + load("samples.json") + load("gemini.json")
    )
    lines = json.loads((HERE / "lines.json").read_text(encoding="utf-8")) if (HERE / "lines.json").exists() else {}
    data = [
        {
            "file": c["file"],
            "line": c["line"],
            "text": c["text"],
            "source": source_of(c),
            "label": c.get("label") or SOURCE_LABEL.get(source_of(c), source_of(c)),
            "accent": accent_of(c),
            "rtf": c.get("rtf"),
            "audio_s": c.get("audio_s"),
            "took_s": c.get("took_s"),
            "direction": c.get("direction"),
        }
        for c in clips
    ]
    # In a JSON script block, with "</" broken so no text can close the tag.
    payload = json.dumps({"clips": data, "lines": lines}).replace("</", r"<\/")
    page = TEMPLATE.replace("__DATA__", payload)
    page = page.replace("__LINE_LABEL__", json.dumps(LINE_LABEL))
    (HERE / "listen.html").write_text(page, encoding="utf-8")
    print(f"listen.html: {len(data)} clips")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interviewer voices — listening test</title>
<style>
  :root { --bg:#f7f7f8; --card:#fff; --ink:#18181b; --soft:#52525b; --faint:#8a8a93; --line:#e4e4e7; --brand:#4f46e5; --brand-soft:#eef2ff; }
  @media (prefers-color-scheme: dark) { :root { --bg:#0b0b0e; --card:#141418; --ink:#ededf0; --soft:#a1a1aa; --faint:#71717a; --line:#26262c; --brand:#8b8cf8; --brand-soft:#1d1d33; } }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 860px; margin: 0 auto; padding: 32px 16px 64px; }
  h1 { font-size: 26px; margin: 0 0 6px; letter-spacing: -0.01em; }
  .sub { color: var(--soft); margin: 0 0 20px; }
  .bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom: 20px; }
  button { font: inherit; border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:10px; padding:7px 12px; cursor:pointer; }
  button.primary { background: var(--brand); border-color: var(--brand); color: #fff; }
  section { background: var(--card); border:1px solid var(--line); border-radius:16px; padding:18px; margin-bottom:16px; }
  h2 { font-size: 16px; margin: 0 0 4px; }
  .text { color: var(--soft); font-size: 14px; margin: 0 0 12px; }
  .row { display:grid; grid-template-columns: 1fr auto; gap: 6px 12px; align-items:center; padding: 10px 0; border-top: 1px solid var(--line); }
  .row:first-of-type { border-top: 0; }
  .who { font-weight: 600; font-size: 14px; }
  .meta { color: var(--faint); font-size: 12px; }
  audio { width: 100%; grid-column: 1 / -1; height: 36px; }
  .vote { display:flex; align-items:center; gap:6px; font-size: 13px; color: var(--soft); }
  .tally { margin-top: 18px; font-size: 14px; }
  .note { color: var(--faint); font-size: 12.5px; margin-top: 24px; }
  .pill { display:inline-block; background: var(--brand-soft); color: var(--brand); border-radius: 999px; padding: 1px 8px; font-size: 12px; margin-left: 6px; }
</style>
</head>
<body>
<main>
  <h1>Which interviewer sounds like a person?</h1>
  <p class="sub">The same lines in each candidate voice. "Today" is the voice students hear now, played live by your browser: open this page in Microsoft Edge for it.</p>
  <div class="bar">
    <button id="blind" class="primary">Blind test: shuffle and hide names</button>
    <button id="reveal" hidden>Reveal names</button>
    <span class="meta" id="mode">Names shown</span>
    <label class="meta">Voices
      <select id="accent"><option value="all">All</option><option value="indian">Indian</option><option value="foreign">Foreign</option></select>
    </label>
  </div>
  <div id="sections"></div>
  <div class="tally" id="tally"></div>
  <p class="note">The Indian voices are six speakers of IndicTTS (SMT Lab, IIT Madras; CC BY 4.0), English recorded by native speakers of Indian languages for speech synthesis, cloned from about 15 seconds each; chosen as the most different of the 21 distinct voices sampled. "Higher" and "lower" describe the pitch of each voice, nothing more.</p>
  <p class="note">The foreign cloned voices are DailyTalk's two speakers (Lee et al., ICASSP 2023; CC BY-SA 4.0), recorded for conversational speech-synthesis research, cloned here from about 12 seconds of their own conversation. Research only: a dataset licence is not a speaker's consent to become a product voice. Chatterbox marks every clip with an inaudible watermark.</p>
  <p class="note">"Written" lines are what the interviewer writes today; "spoken" lines say the same thing the way people talk. Comparing the two shows how much is the voice and how much is the wording. Under each clip: how long this laptop's CPU took to make it. Every clip plays at normal speed; a voice that takes longer to make than to play cannot answer live without a faster computer.</p>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById("data").textContent);
const LINE_LABEL = __LINE_LABEL__;
let blind = false;
let accent = "all";
const votes = {};

function group(lineId) { return lineId.split("_")[0]; }
function shuffle(a) { const b = a.slice(); for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; }

function speakToday(text) {
  const s = window.speechSynthesis; if (!s) return alert("This browser has no speech synthesis.");
  s.cancel();
  const v = s.getVoices().find(v => /Neerja Online/.test(v.name)) || s.getVoices().find(v => v.lang === "en-IN");
  const u = new SpeechSynthesisUtterance(text); if (v) u.voice = v; u.rate = 0.97; s.speak(u);
}

function render() {
  const root = document.getElementById("sections"); root.innerHTML = "";
  const groups = [...new Set(DATA.clips.map(c => group(c.line)))];
  for (const g of groups) {
    const sec = document.createElement("section");
    const lines = [...new Set(DATA.clips.filter(c => group(c.line) === g && (accent === "all" || c.accent === accent)).map(c => c.line))];
    if (!lines.length) continue;
    sec.innerHTML = `<h2>${LINE_LABEL[g] || g}</h2>`;
    for (const lineId of lines) {
      const clips = DATA.clips.filter(c => c.line === lineId && (accent === "all" || c.accent === accent));
      if (!clips.length) continue;
      const text = clips[0].text;
      const style = lineId.endsWith("_written") ? "written, as today" : lineId.endsWith("_sounds") ? "spoken, with a human sound" : lineId.endsWith("_neutral") ? "spoken, no name" : "spoken";
      const block = document.createElement("div");
      block.innerHTML = `<p class="text"><span class="pill">${style}</span> “${text}”</p>`;
      const list = blind ? shuffle([{ today: true, text }, ...clips]) : [{ today: true, text }, ...clips];
      list.forEach((c, i) => {
        const row = document.createElement("div"); row.className = "row";
        const name = blind ? `Voice ${String.fromCharCode(65 + i)}` : (c.today ? "Today · Edge's Neerja voice (live)" : c.label);
        // How long this laptop took to MAKE the clip — not how fast it plays.
        const meta = !blind && !c.today && c.took_s != null
          ? `took ${Math.round(c.took_s)} s to make these ${Math.round(c.audio_s)} s of speech on this laptop` + (c.rtf > 1 ? ` (${c.rtf}× too slow to use live)` : " (fast enough to use live)")
          : "";
        const key = c.today ? "today" : c.source;
        row.innerHTML = `<div><div class="who">${name}</div><div class="meta">${meta}</div></div>
          <label class="vote"><input type="radio" name="${lineId}" value="${key}"> most human</label>`;
        if (c.today) {
          const b = document.createElement("button"); b.textContent = "Play today's voice"; b.style.gridColumn = "1 / -1"; b.onclick = () => speakToday(c.text); row.appendChild(b);
        } else {
          const a = document.createElement("audio"); a.controls = true; a.preload = "none"; a.src = c.file; row.appendChild(a);
        }
        row.querySelector("input").onchange = (e) => { votes[lineId] = e.target.value; tally(); };
        block.appendChild(row);
      });
      sec.appendChild(block);
    }
    root.appendChild(sec);
  }
}

function tally() {
  const counts = {};
  for (const v of Object.values(votes)) counts[v] = (counts[v] || 0) + 1;
  const names = Object.fromEntries(DATA.clips.map(c => [c.source, c.label])); names.today = "Today · Edge's Neerja voice";
  document.getElementById("tally").textContent = Object.keys(counts).length
    ? "Your picks so far: " + Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${blind ? "(hidden)" : names[k] || k} × ${n}`).join(" · ")
    : "";
}

document.getElementById("accent").onchange = (e) => { accent = e.target.value; render(); tally(); };
document.getElementById("blind").onclick = () => { blind = true; document.getElementById("reveal").hidden = false; document.getElementById("blind").hidden = true; document.getElementById("mode").textContent = "Blind: names hidden, order shuffled"; render(); };
document.getElementById("reveal").onclick = () => { blind = false; document.getElementById("reveal").hidden = true; document.getElementById("blind").hidden = false; document.getElementById("mode").textContent = "Names shown"; render(); tally(); };
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
