# What the 3D heads cost the voice (2026-10-12)

**Question.** The room draws each interviewer as a 3D head (gsplat, ~20,000
Gaussians, sorted on the CPU and drawn by the integrated GPU) on the same
laptop that makes the voice. How much does that slow the voice?

**Method.** M11 made two fresh long sentences (~8 s of speech each, live)
while: A, no browser was open; B, a headless room (1440x900, the real page,
two heads) was open; C, the same room with the heads' downloads blocked, so
photos only. The test browser's CPU was sampled over 15 s, picked out by its
own profile folder. The open room also has M11 say its opening and make the
likely next questions, in B and C alike, so B against C is the heads alone.

| | speech made at | test browser CPU |
|---|---|---|
| A, no browser | 1.19x real time | - |
| C, room, photos only | **1.0x** | 0.1 cores (0.6 %) |
| B, room, two 3D heads | **2.2x** | 1.9 cores (11.8 %) |
| B2, the same, paced (Core v0.35.0) | **1.5x** | 0.4 cores (2.3 %) |

**So:** the heads doubled the time to make a reply's voice - more than their
cores account for: the integrated GPU shares the package's power and memory
with the CPU. The renderer draws at the display's rate (60 frames a second)
with no setting for it; Core v0.35.0 paces each head's own loop to 30 frames
a second while it speaks (lip sync is 30 frames a second) and 15 otherwise
(a listener blinks and nods). The browser's CPU fell by 80 %, the slowdown
from +120 % to +50 %. What is left is the GPU's share of the power while it
draws; fewer frames still, or one head drawn and the others as photos, would
take more of it back.
