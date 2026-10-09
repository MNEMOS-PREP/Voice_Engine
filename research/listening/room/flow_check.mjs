// A mock interview, live, timed from the browser: every clip the room puts on
// its Web Audio track (when it starts, how long it sounds), so the silences
// between pieces, between lines and between speakers are measured on the
// audio clock itself — and how long the student waits after each answer.
//
// Reads the plan for READ_S seconds (warm lines are made meanwhile), starts,
// and answers ANSWERS questions, each after THINK_S seconds of "answering".
// Usage: node flow_check.mjs <outDir> <sessionId>
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const [OUT, SID] = process.argv.slice(2);
const READ_S = Number(process.env.READ_S ?? 25);
const THINK_S = Number(process.env.THINK_S ?? 40);
const ANSWERS = Number(process.env.ANSWERS ?? 3);
mkdirSync(OUT, { recursive: true });
const CID = "4d0aa1c0-0000-4000-8000-000000000004";
const PORT = 9431;
const edge = spawn("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", [
  "--headless=new", "--no-first-run", `--user-data-dir=${resolve(OUT)}/edge-${Date.now()}`,
  "--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist",
  "--autoplay-policy=no-user-gesture-required",
  `--remote-debugging-port=${PORT}`, "about:blank",
]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 160; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); if (targets.length) break; } catch {}
  await sleep(250);
}
const page = targets.find((t) => t.type === "page" && t.url === "about:blank") ?? targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const waiting = new Map(); const logs = []; const t0 = Date.now();
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); return; }
  if (msg.method === "Runtime.exceptionThrown") logs.push(`${((Date.now() - t0) / 1000).toFixed(1)}s EXC ` + (msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text).slice(0, 300));
  if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") logs.push(`${((Date.now() - t0) / 1000).toFixed(1)}s error ${msg.params.args.map((a) => a.value ?? a.description).join(" ").slice(0, 200)}`);
};
const send = (method, params = {}) => new Promise((r) => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s]`, ...a);
await send("Page.enable"); await send("Runtime.enable");
await send("Page.addScriptToEvaluateOnNewDocument", { source: `
  window.__clips = []; window.__sent = []; window.__media = [];
  const start = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function (when = 0, offset = 0, duration) {
    const ctx = this.context;
    window.__clips.push({ when, offset, duration: duration ?? (this.buffer ? this.buffer.duration - offset : 0),
      scheduledAt: ctx.currentTime, perf: performance.now(), buffer: this.buffer ? this.buffer.duration : 0 });
    return start.apply(this, arguments);
  };
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { window.__media.push(performance.now()); return play.apply(this, arguments); };
` });
await send("Emulation.setDeviceMetricsOverride", { width: 1300, height: 950, deviceScaleFactor: 1, mobile: false });
const click = (t) => ev(`(() => { const b = [...document.querySelectorAll("button")].find(b => (b.getAttribute("aria-label") || b.textContent.trim()).startsWith(${JSON.stringify(t)}) && !b.disabled); if (!b) return "missing"; b.click(); return "ok"; })()`);
await send("Page.navigate", { url: `http://localhost:5173/mock/${SID}/plan?as=student&candidate=${CID}` });
log(`reading the plan for ${READ_S} s`);
await sleep(READ_S * 1000);
for (let i = 0; i < 30; i++) { if ((await click("Start the interview")) === "ok") { log("started"); break; } await sleep(1000); }
const busy = () => ev(`(() => { const c = window.__clips; if (!c.length) return false; const ctxNow = c[c.length - 1].scheduledAt + (performance.now() - c[c.length - 1].perf) / 1000; return c.some(x => x.when + x.duration > ctxNow - 0.05); })()`);
async function waitForTurn(label, clipsBefore = 0) {
  // The reply's first sound (a clip newer than the answer), then the question
  // open and nothing on the track for 2 s. The answer box opens when the line
  // lands, before its audio: waiting on the box alone ended turns early.
  for (let i = 0; i < 480; i++) {
    const heard = (await ev(`window.__clips.length`)) > clipsBefore;
    const open = await ev(`[...document.querySelectorAll("textarea")].some(t => !t.disabled)`);
    if (heard && open && !(await busy())) {
      await sleep(2000);
      if (!(await busy())) { log(`${label}: turn open`); return true; }
    }
    await sleep(500);
  }
  log(`${label}: timed out`);
  return false;
}
const ANSWER_TEXT = [
  "A process is a running program with its own address space, while threads share the address space of their process, so switching between threads is cheaper but they need synchronisation.",
  "When two threads update shared data without a lock, a race condition can corrupt it, so I would use a mutex or an atomic operation around the critical section.",
  "Virtual memory gives each process the illusion of a large private address space; the page table maps virtual pages to frames and a page fault loads a missing page from disk.",
];
await waitForTurn("opening");
for (let n = 0; n < ANSWERS; n++) {
  log(`answering question ${n + 1} after ${THINK_S} s`);
  await sleep(THINK_S * 1000);
  const text = ANSWER_TEXT[n % ANSWER_TEXT.length];
  await ev(`(() => { const t = [...document.querySelectorAll("textarea")].find(t => !t.disabled); const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set; set.call(t, ${JSON.stringify(text)}); t.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`);
  await sleep(300);
  const before = await ev(`window.__clips.length`);
  await ev(`window.__sent.push(performance.now())`);
  log("sent:", await click("Answer"));
  await waitForTurn(`after answer ${n + 1}`, before);
}
const data = await ev(`({ clips: window.__clips, sent: window.__sent, media: window.__media })`);
const said = await ev(`[...document.querySelectorAll(".turn-interviewer")].map(e => e.innerText.slice(0, 160))`);
writeFileSync(`${OUT}/flow.json`, JSON.stringify({ ...data, said }, null, 1));
// ── the numbers ──
const clips = [...data.clips].sort((a, b) => a.when - b.when).map((c) => ({ ...c, end: c.when + c.duration, startPerf: c.perf + (c.when - c.scheduledAt) * 1000 }));
const gaps = [];
for (let i = 1; i < clips.length; i++) gaps.push(+(clips[i].when - clips[i - 1].end).toFixed(3));
const inLine = gaps.filter((g) => g < 2.5);
console.log(`clips: ${clips.length}; gaps between consecutive clips (s): ${JSON.stringify(gaps)}`);
console.log(`within lines (<2.5 s): max ${Math.max(...inLine).toFixed(2)} s, over 0.6 s: ${inLine.filter((g) => g > 0.6).length} of ${inLine.length}`);
for (const sentAt of data.sent) {
  const first = clips.find((c) => c.startPerf > sentAt);
  console.log(`answer sent -> first sound: ${first ? ((first.startPerf - sentAt) / 1000).toFixed(2) : "none"} s`);
}
console.log(`browser-voice or backchannel <audio> plays: ${data.media.length}`);
for (const l of logs.slice(0, 12)) console.log("  ", l);
edge.kill();
process.exit(0);
