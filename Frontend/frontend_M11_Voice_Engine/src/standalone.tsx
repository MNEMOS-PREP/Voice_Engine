/**
 * M11 running alone on :5211.
 *
 * Same routes and components as the shell mounts; this file only supplies the
 * providers the shell would otherwise own.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SEEDED_CANDIDATE_ID, ensureSession } from "@ai/core";

import { m11Routes } from "./routes";
import { AppShell } from "./ui/AppShell";
// One stylesheet, on purpose: theme.css imports @ai/core/styles.css itself.
import "./ui/theme.css";

// Alone there is no sign-in screen, so with nobody signed in this is the
// seeded student (`@ai/core`'s session).
ensureSession({ role: "student", subject: SEEDED_CANDIDATE_ID });

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell>
          <Routes>
            {m11Routes}
            <Route path="*" element={<Navigate to="/voice" replace />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
