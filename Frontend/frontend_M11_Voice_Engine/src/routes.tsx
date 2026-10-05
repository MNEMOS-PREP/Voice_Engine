/**
 * M11 — routes. Mounted whole by Platform_Shell, and by `standalone.tsx`.
 *
 * `/voice`, the same word as the module's `/v1/voice` noun.
 */

import { Route } from "react-router-dom";

import { VoiceCheck } from "./components/VoiceCheck";

export const m11Routes = (
  <Route key="m11">
    <Route path="/voice" element={<VoiceCheck />} />
  </Route>
);
