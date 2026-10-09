# The interview room, measured live (2026-10-09)

Headless Edge driven over the DevTools protocol (Node 22+, no packages), with
the stack running (shell on :5173, M06, M11).

- `flow_check.mjs <outDir> <sessionId>` — a mock: reads the plan, starts,
  answers by typing; records every clip the room puts on its Web Audio track,
  so the silences between pieces, lines and speakers are measured on the audio
  clock, and how long each answer waits for the first sound.
  `READ_S`, `THINK_S`, `ANSWERS` in the environment.
- `room_sync.mjs <outDir> <sessionId> <rendererModuleUrl>` — lip sync: wraps
  the renderer's `create` from the test side (nothing in the product) and
  records, every frame, the mouth each head was given against the audio's
  clock. `rendererModuleUrl` is the shell's vite dep URL,
  `/node_modules/.vite/deps/@myned-ai_gsplat-flame-avatar-renderer.js?v=<hash>`
  (`_metadata.json`'s browserHash). Written for the `<audio>` player (Core
  v0.28); the v0.29 track needs it to read the Web Audio clock instead.

What they found is in `../gaps.md`.
