"use client";

import { useCallback, useEffect, useState } from "react";
import { api, MovementMode } from "@/lib/api";

const SQUAT: MovementMode = {
  id: "squat",
  label: "Squat",
  watches: "depth, trunk lean, range of motion, knees, heels, tempo",
  view: "side",
  validated: true,
  selectable: true,
  note: null,
};

// Every hook instance hears about a mode change made anywhere on the page.
const listeners = new Set<(mode: string) => void>();

/**
 * The saved movement mode (session defaults) and the list of modes.
 * Only modes the backend marks selectable can be picked; the rest are shown
 * as coming, with the reason. Squat is the default and the fallback.
 */
export function useMovementMode() {
  const [modes, setModes] = useState<MovementMode[]>([SQUAT]);
  const [mode, setModeState] = useState<string>("squat");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings.movementModes().then((r) => setModes(r.modes)).catch(() => {});
    api.settings.get().then((d) => setModeState(d.movement_mode || "squat")).catch(() => {});
    const hear = (m: string) => setModeState(m);
    listeners.add(hear);
    return () => {
      listeners.delete(hear);
    };
  }, []);

  const setMode = useCallback(async (next: string) => {
    setError(null);
    try {
      const saved = await api.settings.update({ movement_mode: next });
      listeners.forEach((l) => l(saved.movement_mode));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change the movement mode");
    }
  }, []);

  const current = modes.find((m) => m.id === mode) ?? SQUAT;
  return { modes, mode, current, setMode, error };
}
