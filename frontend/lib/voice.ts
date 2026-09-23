// Spoken cues, played by the browser that shows the live page.
//
// The backend's own voice (pyttsx3) speaks on the backend machine's
// speakers. Through a hosted link that machine is a server with no audio,
// and its cues come from the older risk model rather than the rep flags
// the screen shows. So the live page speaks the same things the screen
// shows, with the browser's built-in speech (speechSynthesis), on the
// device the lifter is actually looking at. Sessions started from the web
// ask the backend to stay quiet so a local laptop doesn't speak twice.
import { useCallback, useEffect, useRef, useState } from "react";
import { FLAG_CUE } from "@/components/lg/ui";

const KEY = "lg.voice"; // "on" (default) | "off"

function synth(): SpeechSynthesis | null {
  return typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
}

export function speak(text: string) {
  const s = synth();
  if (!s) return;
  // A new cue replaces one still waiting: late cues are wrong cues.
  s.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  s.speak(u);
}

/**
 * Browsers only allow speech after the user has pressed something on the
 * page. Call this inside the click/key handler that starts a session.
 */
export function unlockVoice() {
  const s = synth();
  if (!s) return;
  const u = new SpeechSynthesisUtterance(" ");
  u.volume = 0;
  s.speak(u);
}

export function useVoiceSetting() {
  const [on, setOn] = useState(true);
  useEffect(() => {
    try {
      setOn(localStorage.getItem(KEY) !== "off");
    } catch {
      /* private mode: keep the default */
    }
  }, []);
  const toggle = useCallback(() => {
    setOn((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(KEY, next ? "on" : "off");
      } catch {
        /* ignore */
      }
      if (next) speak("Voice on");
      else synth()?.cancel();
      return next;
    });
  }, []);
  return { voiceOn: on, toggleVoice: toggle, voiceSupported: synth() !== null };
}

type Status = {
  warmingUp: boolean;
  manualCal: boolean;
  lastRep: { rep?: number; form_flags?: string[] } | null;
  fatigueStatus: string | null;
};

/**
 * Speaks what the stage shows, when it changes:
 * - warm-up finished: "Counting"
 * - a flagged rep: its short command ("Go deeper", "Chest up", "Full range")
 * - every 5th clean rep: "5 reps"
 * - fatigue indicator turns elevated: "Fatigue indicator up"
 * Nothing is spoken while learning depth (the first 3 slow squats).
 */
export function useVoiceCues(status: Status | null, enabled: boolean) {
  const prev = useRef<{ warm: boolean; rep: number | null; fatigue: string | null } | null>(null);
  useEffect(() => {
    if (!status) {
      prev.current = null;
      return;
    }
    const warm = status.warmingUp || status.manualCal;
    const rep = status.lastRep?.rep ?? null;
    const p = prev.current;
    prev.current = { warm, rep, fatigue: status.fatigueStatus };
    if (!p || !enabled) return; // first telemetry only sets the baseline
    const flags = status.lastRep?.form_flags ?? [];
    const newRep = rep != null && rep !== p.rep;
    const cue = newRep && flags.length ? FLAG_CUE[flags[0]]?.cue : null;
    // Warm-up often ends on the same update that counts the first reps, so
    // check it alongside a new rep, not instead of it. A flag wins.
    if (cue) speak(cue);
    else if (p.warm && !warm) speak("Counting");
    else if (newRep && rep % 5 === 0) speak(`${rep} reps`);
    else if (status.fatigueStatus === "ELEVATED" && p.fatigue !== "ELEVATED") {
      speak("Fatigue indicator up");
    }
  }, [status, enabled]);
}
