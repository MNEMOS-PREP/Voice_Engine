/**
 * The frame when M11 runs alone on :5211. In Platform_Shell the shell's frame
 * replaces it; the routes inside are the same.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { DependencyAlert } from "@ai/core";

import { useDeps } from "../api";

export function AppShell({ children }: { children: ReactNode }) {
  const deps = useDeps();
  const degraded = (deps.data ?? [])
    .filter((row) => !row.available)
    .map((row) => ({
      feature: "voice check",
      needs_module: row.module_id,
      needs_module_name: row.name,
      explanation: row.on_missing,
    }));
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-12 max-w-4xl items-center gap-4 px-4 text-sm">
          <Link to="/voice" className="font-semibold text-ink">
            M11 · Voice
          </Link>
          <span className="text-ink-faint">standalone on :5211 - the shell on :5173 mounts the same screens</span>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-8">
        <DependencyAlert degraded={degraded} />
        {children}
      </main>
    </div>
  );
}
