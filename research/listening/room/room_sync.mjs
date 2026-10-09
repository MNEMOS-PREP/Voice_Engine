// The room, live: is the face each head is given, frame by frame, the face
// for the audio's own time? A test-side hook (nothing added to the product):
// the renderer module the room imports is imported first, at the same URL,
// and its `create` wrapped, so every frame's expression is recorded with the
// playing audio's currentTime. The face frames the page fetches are kept too,
// so the analysis can say which sentence each frame came from and how far the
// applied mouth is from the one for that moment.
//
// Usage: node room_sync.mjs <outDir> <sessionId> <rendererModuleUrl>
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const [OUT, SID, MODULE] = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });
const CID = "4d0aa1c0-0000-4000-8000-000000000004";
const PORT = 9421;
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
  if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
    logs.push(`${((Date.now() - t0) / 1000).toFixed(1)}s error ${msg.params.args.map((a) => a.value ?? a.description).join(" ").slice(0, 200)}`);
  }
};
const send = (method, params = {}) => new Promise((r) => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s]`, ...a);
await send("Page.enable"); await send("Runtime.enable");
await send("Page.addScriptToEvaluateOnNewDocument", { source: `
  window.__audios = []; window.__trace = []; window.__faces = {}; window.__created = [];
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { if (!window.__audios.includes(this)) window.__audios.push(this); return play.apply(this, arguments); };
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    const response = await originalFetch.apply(this, arguments);
    const url = typeof input === "string" ? input : input.url;
    const match = /\\/v1\\/voice\\/face\\/([0-9a-f]+)/.exec(url || "");
    if (match && response.ok) response.clone().json().then((j) => { window.__faces[match[1]] = j; }).catch(() => {});
    return response;
  };
  import(${JSON.stringify(MODULE)}).then((module) => {
    const C = module.GaussianSplatRenderer;
    const create = C.create.bind(C);
    C.create = async (container, url, options) => {
      const persona = decodeURIComponent(String(url).split("/").pop().replace(/\\.zip$/, ""));
      const get = options.getExpressionData;
      const wrapped = { ...options, getExpressionData: () => {
        const e = get();
        const a = window.__audios.at(-1);
        window.__trace.push([persona, +performance.now().toFixed(1), a ? +a.currentTime.toFixed(4) : null, a ? (a.paused || a.ended) : true, window.__audios.length - 1, +(e.jawOpen || 0).toFixed(4), +(e.mouthLowerDownLeft || 0).toFixed(4), +(e.eyeBlinkLeft || 0).toFixed(3)]);
        return e;
      } };
      window.__created.push(persona);
      return create(container, url, wrapped);
    };
    window.__hooked = true;
  });
` });
await send("Emulation.setDeviceMetricsOverride", { width: 1300, height: 950, deviceScaleFactor: 1, mobile: false });
const click = (t) => ev(`(() => { const b = [...document.querySelectorAll("button")].find(b => (b.getAttribute("aria-label") || b.textContent.trim()).startsWith(${JSON.stringify(t)}) && !b.disabled); if (!b) return "missing"; b.click(); return "ok"; })()`);
await send("Page.navigate", { url: `http://localhost:5173/mock/${SID}/plan?as=student&candidate=${CID}` });
for (let i = 0; i < 60; i++) {
  if ((await click("Start the interview")) === "ok") { log("started; hooked:", await ev("window.__hooked")); break; }
  await sleep(1000);
}
const tiles = `[...document.querySelectorAll("figure")]`;
for (let i = 0; i < 150; i++) {
  const heads = await ev(`${tiles}.filter(f => f.querySelector("canvas") && !f.querySelector(".opacity-0")).length`);
  const open = await ev(`[...document.querySelectorAll("button")].some(b => b.textContent.trim().startsWith("Repeat the question") && !b.disabled)`);
  if (heads >= 2 && open) { log("heads ready:", heads, "created:", JSON.stringify(await ev("window.__created"))); break; }
  await sleep(1000);
}
await sleep(1500);
const mark = await ev("window.__trace.length");
log("repeat:", await click("Repeat the question"));
for (let i = 0; i < 80; i++) {
  if (await ev(`${tiles}.some(f => f.className.includes("ring-2"))`)) break;
  await sleep(250);
}
for (let i = 0; i < 160; i++) {
  if (!(await ev(`${tiles}.some(f => f.className.includes("ring-2"))`))) break;
  await sleep(250);
}
log("speech over; waiting 6 s for the after-speech and blinks");
await sleep(6000);
const data = await ev(`({ trace: window.__trace.slice(${mark}), faces: window.__faces, audios: window.__audios.map((a) => a.duration) })`);
writeFileSync(`${OUT}/sync.json`, JSON.stringify(data));
log("trace rows:", data.trace.length, "faces fetched:", Object.keys(data.faces).length, "audios:", data.audios.length);
for (const l of logs.slice(0, 20)) console.log("  ", l);
edge.kill();
process.exit(0);
