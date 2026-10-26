// M11's latency harness — day 14 (TODO §7): a spoken panel interview in a
// real page, graded against the spec's gates by M11's own ledger.
//
// It sits a whole mock in headless Edge (or Chrome) through the shell, as a
// student would: the panel's opening, typed answers until the round comes
// back to the lead, then SPOKEN answers — sentence by sentence, with a
// speaker's gaps — into a microphone stream this script controls. Then it
// asks M11 for the interview's ledger summary (`/v1/voice/timings/summary
// ?session_id=`, the same targets as the staff page) and prints each stage
// against its target, with what the room did on the way: hand-overs, the
// asides ("okay"), answers kept, and errors.
//
// Network chaos (spec §16): `--profile 3g|2g` throttles the page through the
// DevTools protocol once the opening is said — the browser reports it to the
// page as its connection; on 2g the room must move to hold-to-talk
// (FR-11.17) mid-interview, and the harness checks that it did.
//
// Needs the stack running (start_all.bat): shell :5173, M06, M11 (voice
// ready), M01/M02/M04/M05 for a planned interview. Answers come from a model
// on Groq when a key is in keys.txt, else from a canned set.
//
//   node scripts/latency_harness.mjs [--candidate <uuid>] [--mode mock]
//        [--minutes 20] [--spoken 3] [--max 14] [--profile good|3g|2g]
//        [--out <dir>]
//
// Writes <out>/latency-<session>.json and screenshots; exit code 1 when a
// gate with a target is over it, 2 when the run itself failed.

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((out, arg, i, all) => {
    if (arg.startsWith("--")) out.push([arg.slice(2), all[i + 1]?.startsWith("--") ? "1" : all[i + 1]]);
    return out;
  }, []),
);
const SHELL = args.shell ?? "http://localhost:5173";
const M06 = args.m06 ?? "http://127.0.0.1:8106";
const M11 = args.m11 ?? "http://127.0.0.1:8111";
const M04 = args.m04 ?? "http://127.0.0.1:8104";
const CANDIDATE = args.candidate ?? "4d0aa1c0-0000-4000-8000-000000000004";
const MODE = args.mode ?? "mock";
const MINUTES = Number(args.minutes ?? 20);
const SPOKEN = Number(args.spoken ?? 3);
const MAX = Number(args.max ?? 14);
const PROFILE = args.profile ?? "good";
const OUT = resolve(args.out ?? join(tmpdir(), "m11-latency"));
mkdirSync(OUT, { recursive: true });

const PROFILES = {
  good: null,
  "3g": { offline: false, latency: 300, downloadThroughput: 94000, uploadThroughput: 47000, connectionType: "cellular3g" },
  "2g": { offline: false, latency: 1600, downloadThroughput: 25000, uploadThroughput: 12000, connectionType: "cellular2g" },
};
if (!(PROFILE in PROFILES)) throw new Error(`--profile is one of ${Object.keys(PROFILES).join(", ")}`);

const WHO = { "X-Role": "student", "X-Candidate-Id": CANDIDATE };
const STAFF = { "X-Role": "admin", "X-Candidate-Id": "ops" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = Date.now();
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(0)}s]`, ...a);

function groqKey() {
  for (const path of [resolve("keys.txt"), resolve("..", "keys.txt"), resolve("..", "..", "keys.txt")]) {
    if (!existsSync(path)) continue;
    const m = /^GROQ_API_KEYS?\s*=\s*"?([^",\r\n]+)/m.exec(readFileSync(path, "utf8"));
    if (m) return m[1];
  }
  return process.env.GROQ_API_KEY ?? null;
}
const GROQ = groqKey();

const CANNED = [
  "The loop visits each of the n elements once and does constant work each time. So the total work grows linearly with n. That makes it O of n.",
  "I built a civic grievance system with Django and React. A DeBERTa classifier routes each complaint to one of twenty departments. It reached about ninety percent accuracy.",
  "A hash map hashes the key to find a bucket, then looks inside that bucket. With a good hash function the buckets stay small. So a lookup is constant time on average.",
  "I would profile first to see where the time goes. Then I would cache the classifier's results for repeated complaints. And I would batch the database writes.",
];

async function answerFor(question, n) {
  if (!GROQ) return CANNED[n % CANNED.length];
  try {
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${GROQ}`, "Content-Type": "application/json", "User-Agent": "AI-Interviewer/1.0" },
      body: JSON.stringify({
        model: "openai/gpt-oss-120b",
        messages: [
          { role: "system", content: "You are a well-prepared final-year CS student in a placement interview. Answer the interviewer's last question directly in 3 spoken sentences, first person, no lists, no markdown. Projects: a civic grievance system (Django, React, DeBERTa routing complaints to 20 departments, 90% accuracy); a diabetic retinopathy grading pipeline (EfficientNet-B3, radiomics cross-attention, CORAL loss)." },
          { role: "user", content: question },
        ],
        max_tokens: 400,
      }),
    });
    const j = await r.json();
    const text = j.choices?.[0]?.message?.content?.replace(/\s+/g, " ").trim();
    return text || CANNED[n % CANNED.length];
  } catch {
    return CANNED[n % CANNED.length];
  }
}

/** A voice nobody on this panel has spoken in: M11's roster, less the voices
 *  the room has played. Asked of M11, not named here — "dailytalk-0" was
 *  retired (2026-10-11) and an unknown voice is quietly the default one,
 *  which two panelists speak in. */
let studentVoice = null;
async function voiceForStudent() {
  if (studentVoice) return studentVoice;
  const roster = (await (await fetch(`${M11}/v1/voice/cast`, { headers: WHO })).json()).voices.map((v) => v.key);
  const panel = new Set(((await ev("window.__speak")) ?? []).map((s) => s.voice));
  studentVoice = roster.find((key) => !panel.has(key)) ?? roster.at(-1);
  return studentVoice;
}

/** A student's sentence, in a voice nobody on the panel has. */
async function voiced(sentence) {
  const r = await fetch(`${M11}/v1/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...WHO },
    body: JSON.stringify({ text: sentence.slice(0, 390), voice: await voiceForStudent() }),
  });
  if (!r.ok) throw new Error(`M11 could not voice the student (${r.status})`);
  return Buffer.from(await r.arrayBuffer()).toString("base64");
}

// ── the interview ─────────────────────────────────────────────────────────

// A student who was never welcomed is sent to the welcome step, not the
// interview (the shell's gate). The harness's own student is marked welcomed
// in M04 — and given no consent, so its interviews move nobody's skill graph.
try {
  const profile = await (await fetch(`${M04}/v1/candidates/${CANDIDATE}/profile`, { headers: WHO })).json();
  if (!profile?.onboarded_at) {
    await fetch(`${M04}/v1/candidates/${CANDIDATE}/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...WHO },
      body: JSON.stringify({ display_name: "Latency harness", onboarded: true }),
    });
  }
} catch {
  /* M04 not running: the shell will say so at the gate below */
}

const created = await fetch(`${M06}/v1/interviews`, {
  method: "POST",
  headers: { "Content-Type": "application/json", ...WHO },
  body: JSON.stringify({ mode: MODE, minutes: MINUTES }),
});
const session = await created.json();
if (!created.ok) {
  console.error("M06 would not create the interview:", JSON.stringify(session.detail ?? session));
  process.exit(2);
}
const SID = session.id;
log(`interview ${SID} (${MODE}, ${MINUTES} min, network ${PROFILE})`);

const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
];
const PORT = 9360 + Math.floor(Math.random() * 30);
const browser = spawn(BROWSERS.find((b) => existsSync(b)), [
  "--headless=new", "--disable-gpu", "--no-first-run", `--user-data-dir=${join(OUT, `profile-${SID}`)}`,
  "--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream", `--remote-debugging-port=${PORT}`, "about:blank",
]);
let targets;
for (let i = 0; i < 60; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); if (targets.length) break; } catch {}
  await sleep(250);
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0;
const waiting = new Map();
const errors = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); }
  else if (msg.method === "Runtime.exceptionThrown") errors.push(msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text);
};
const send = (method, params = {}) => new Promise((r) => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const shot = async (name) => {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, `${name}.png`), Buffer.from(r.result.data, "base64"));
};

await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");
await send("Page.addScriptToEvaluateOnNewDocument", { source: `
  try { localStorage.setItem("m06.talkFreely", "on"); localStorage.setItem("m11.keepAnswers", "on"); } catch {}
  window.__speak = []; window.__kept = [];
  const f = window.fetch;
  window.fetch = async (u, o) => {
    const url = String(u);
    const r = await f(u, o);
    if (url.includes("/v1/voice/speak")) {
      let body = {}; try { body = JSON.parse(o.body); } catch {}
      window.__speak.push({ persona: body.persona_id, text: body.text, voice: r.headers.get("x-voice"), cache: r.headers.get("x-cache") });
    }
    if (/\\/v1\\/voice\\/[^/]+\\/audio/.test(url)) window.__kept.push({ method: (o && o.method) || "GET", status: r.status });
    return r;
  };
  window.__asides = 0;
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { if (this.volume < 1) window.__asides += 1; return play.call(this); };
  window.__ctx = null; window.__dest = null;
  navigator.mediaDevices.getUserMedia = async () => {
    window.__ctx = window.__ctx || new AudioContext({ sampleRate: 48000 });
    window.__dest = window.__dest || window.__ctx.createMediaStreamDestination();
    return window.__dest.stream;
  };
  window.__sayAll = async (clips, gapMs) => {
    let at = window.__ctx.currentTime + 0.05; let total = 0;
    for (const b64 of clips) {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const buffer = await window.__ctx.decodeAudioData(bytes.buffer);
      const src = window.__ctx.createBufferSource();
      src.buffer = buffer; src.connect(window.__dest); src.start(at);
      at += buffer.duration + gapMs / 1000; total += buffer.duration + gapMs / 1000;
    }
    return Math.round(total * 10) / 10;
  };
`});
await send("Emulation.setDeviceMetricsOverride", { width: 1200, height: 1400, deviceScaleFactor: 1, mobile: false });

const click = (t) => ev(`(() => { const b = [...document.querySelectorAll("button")].find(b => (b.getAttribute("aria-label") || b.textContent.trim()).startsWith(${JSON.stringify(t)}) && !b.disabled); if (!b) return "missing"; b.click(); return "ok"; })()`);
const bubbles = () => ev(`[...document.querySelectorAll(".turn-interviewer")].map(el => (el.classList.contains("text-ink-soft") ? "~" : "") + (el.parentElement.querySelector("p")?.innerText || "?") + ": " + el.innerText.replace(/\\s+/g, " "))`);
const answers = () => ev(`document.querySelectorAll(".turn-candidate").length`);
const speaking = () => ev(`[...document.querySelectorAll("span")].some(s => s.textContent === "Speaking")`);
const open = () => ev(`(() => { const t = document.querySelector("#answer"); return !!t && !t.disabled; })()`);
const dots = () => ev(`document.querySelectorAll(".thinking-dot").length > 0`);
const over = () => ev(`[...document.querySelectorAll("button")].some(b => b.textContent.includes("See the notes"))`);
const holdMode = () => ev(`[...document.querySelectorAll("button")].some(b => b.textContent.includes("Hold to talk") && b.getAttribute("aria-pressed") === "true")`);
const typeAnswer = (text) => ev(`(() => { const t = document.querySelector("#answer"); const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set; set.call(t, ${JSON.stringify(text)}); t.dispatchEvent(new Event("input", { bubbles: true })); document.querySelector("form").requestSubmit(); })()`);

let seen = [];
const shown = [];
/** Lines as they appear, timed from `from`, until a new one has been said. */
async function watch(from, sentBefore = null) {
  const before = seen.length;
  let quietSince = null;
  for (let i = 0; i < 1200; i++) {
    await sleep(250);
    const all = (await bubbles()) ?? [];
    for (let k = 0; k < all.length; k++) {
      if (seen[k] !== all[k]) {
        const t = (Date.now() - from) / 1000;
        console.log(`   +${t.toFixed(1)}s ${all[k].slice(0, 200)}`);
        shown.push({ t, line: all[k] });
      }
    }
    seen = all;
    if ((await over()) && !(await speaking())) return;
    const sent = sentBefore === null || ((await answers()) ?? 0) > sentBefore;
    const fresh = all.slice(before).some((b) => !b.startsWith("~"));
    const done = sent && fresh && (await open()) && !(await speaking()) && !(await dots());
    if (done) { quietSince ??= Date.now(); if (Date.now() - quietSince > 2500) return; }
    else quietSince = null;
  }
}

try {
  await send("Page.navigate", { url: `${SHELL}/mock/${SID}/plan?as=student&candidate=${CANDIDATE}` });
  await sleep(8000);
  const started = await click("Start the interview");
  log("Start:", started);
  if (started !== "ok") throw new Error(`no Start button at ${await ev("location.pathname")}`);
  await watch(Date.now());
  await shot(`latency-${SID}-opening`);
  if (PROFILES[PROFILE]) {
    // The connection degrades mid-interview, as a hostel's does — and the
    // page hears of it the way it would (navigator.connection's change).
    await send("Network.emulateNetworkConditions", PROFILES[PROFILE]);
    await sleep(2000);
    log(`network now ${PROFILE}:`, JSON.stringify(await ev(`({ type: navigator.connection?.effectiveType, rtt: navigator.connection?.rtt })`)));
  }
  let spokenSoFar = 0;
  for (let n = 1; n <= MAX && !(await over()); n++) {
    const all = (await bubbles()) ?? [];
    const asked = all.filter((b) => !b.startsWith("~")).at(-1) ?? "";
    const sentBefore = (await answers()) ?? 0;
    if (/Do you have any|questions for us|Anything you'd like to ask|Your questions\?/i.test(asked)) {
      log("closing — the student has nothing to ask");
      await typeAnswer("No, that's all from me. Thank you.");
      await watch(Date.now());
      break;
    }
    const back = all.some((b) => /^[^:]+: Thanks, /.test(b) && all.indexOf(b) > 1);
    const reply = await answerFor(asked.replace(/^[^:]*: /, ""), n);
    // Spoken after the round comes back to the lead — or, on a panel with
    // no hand-over to wait for (a student with no resume), after two typed.
    const spoken = (back || n > 2) && spokenSoFar < SPOKEN && !(await holdMode());
    let from;
    if (spoken) {
      spokenSoFar += 1;
      const sentences = reply.match(/[^.!?]+[.!?]+/g)?.map((s) => s.trim()).filter(Boolean) ?? [reply];
      const clips = [];
      for (const s of sentences) clips.push(await voiced(s));
      const secs = await ev(`window.__sayAll(${JSON.stringify(clips)}, 420)`);
      log(`YOU (spoken, ${sentences.length} sentences, ${secs}s): ${reply.slice(0, 120)}`);
      await sleep(Math.max(0, secs * 1000 - 400));
      from = Date.now();
    } else {
      log(`YOU (typed): ${reply.slice(0, 120)}`);
      from = Date.now();
      await typeAnswer(reply);
    }
    await watch(from, sentBefore);
  }
} catch (exc) {
  errors.push(String(exc));
}
await shot(`latency-${SID}-final`);

// ── the grade ─────────────────────────────────────────────────────────────

const page = {
  holdToTalk: await holdMode(),
  asides: (await ev(`window.__asides`)) ?? 0,
  kept: (await ev(`window.__kept`)) ?? [],
  speak: (await ev(`window.__speak`)) ?? [],
};
ws.close();
browser.kill();
// However it went, the interview is over: an open one blocks the next run.
await fetch(`${M06}/v1/interviews/${SID}/end`, { method: "POST", headers: WHO }).catch(() => undefined);
await sleep(3000); // the last line's record reaches the ledger
const summary = await (await fetch(`${M11}/v1/voice/timings/summary?days=1&session_id=${SID}`, { headers: STAFF })).json();
// M06's side of the run: the prefills (FR-11.6, AC-11.7's cancel rate) and
// the questions asked about rather than judged (FR-11.16, EC-11.1).
const sat = await (await fetch(`${M06}/v1/interviews/${SID}`, { headers: WHO })).json().catch(() => ({ transcript: [] }));
const answered = (sat.transcript ?? []).filter((t) => t.role === "candidate");
const prefill = {
  tried: answered.reduce((n, t) => n + (t.prefill?.tried ?? 0), 0),
  used: answered.filter((t) => t.prefill?.used).length,
};
const asked = (sat.transcript ?? []).filter((t) => t.role === "interviewer");
const askedAbout = {
  clarify_term: asked.filter((t) => t.probe_move === "clarify_term").length,
  reoffer: asked.filter((t) => t.probe_move === "reoffer").length,
  didnt_catch: asked.filter((t) => t.probe_move === "didnt_catch").length,
};
const voices = {};
for (const s of page.speak) (voices[s.persona] ??= new Set()).add(s.voice);
const report = {
  session_id: SID,
  mode: MODE,
  network: PROFILE,
  summary,
  handovers: shown.filter((s) => /over to you/i.test(s.line)).length,
  voices: Object.fromEntries(Object.entries(voices).map(([k, v]) => [k, [...v]])),
  asides_played: page.asides,
  kept: page.kept,
  hold_to_talk: page.holdToTalk,
  prefill,
  asked_about: askedAbout,
  errors,
};
writeFileSync(join(OUT, `latency-${SID}.json`), JSON.stringify(report, null, 1));

console.log(`\nM11 latency — interview ${SID}, network ${PROFILE}`);
console.log(`${summary.lines} lines spoken; hand-overs ${report.handovers}; asides ${page.asides}; voices ${JSON.stringify(report.voices)}`);
console.log("stage                p50     p95   target  gate");
let over_budget = false;
for (const s of summary.stages ?? []) {
  if (!s.n) continue;
  const verdict = s.met === null ? "" : s.met ? "ok" : "OVER";
  if (s.met === false) over_budget = true;
  console.log(`${s.name.padEnd(18)} ${String(s.p50).padStart(6)}  ${String(s.p95).padStart(6)}  ${String(s.target_ms ?? "—").padStart(6)}  ${(s.gate ?? "").padEnd(8)} ${verdict}  (n=${s.n})`);
}
if (prefill.tried) {
  const cancelled = Math.round((100 * (prefill.tried - prefill.used)) / prefill.tried);
  console.log(`prefill: ${prefill.used} used of ${prefill.tried} tried — cancel rate ${cancelled}% (AC-11.7: 25–40%)`);
}
console.log(`asked about, not judged: ${JSON.stringify(askedAbout)}`);
if (PROFILE === "2g") console.log(`2g: hold-to-talk ${page.holdToTalk ? "engaged" : "NOT engaged"} (FR-11.17)`);
if (errors.length) console.log("errors:", JSON.stringify(errors));
console.log(`report: ${join(OUT, `latency-${SID}.json`)}`);
process.exit(errors.length ? 2 : PROFILE === "2g" && !page.holdToTalk ? 1 : over_budget ? 1 : 0);
