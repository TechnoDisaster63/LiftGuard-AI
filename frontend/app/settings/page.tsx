"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { API_BASE, api, SessionDefaults } from "@/lib/api";
import OptionWheel from "@/components/reactbits/OptionWheel";
import { Card } from "@/components/ui/card";

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-3">
      <div>
        <p className="text-sm text-ink">{label}</p>
        {description && <p className="text-[11px] text-ink-faint mt-0.5">{description}</p>}
      </div>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`w-10 h-6 rounded-full relative transition-colors ${
          checked ? "bg-brand" : "bg-panel-raised border border-border"
        }`}
      >
        <span
          className={`absolute top-0.5 w-5 h-5 rounded-full bg-void transition-transform ${
            checked ? "translate-x-[18px] bg-void" : "translate-x-0.5 bg-ink-faint"
          }`}
        />
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const [health, setHealth] = useState<string>("checking…");
  const [defaults, setDefaults] = useState<SessionDefaults | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then((d) => setHealth(d.status))
      .catch(() => setHealth("unreachable"));
    api.settings.get().then(setDefaults).catch((e) => setError(e.message));
  }, []);

  const patch = async (fields: Partial<SessionDefaults>) => {
    if (!defaults) return;
    const next = { ...defaults, ...fields };
    setDefaults(next); // optimistic
    setSaving(true);
    setError(null);
    try {
      const saved = await api.settings.update(fields);
      setDefaults(saved);
      setSavedAt(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-lg">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="p-6">
        <p className="font-display text-lg mb-1">Backend Connection</p>
        <p className="text-sm text-ink-muted mb-4">These pages call {API_BASE}</p>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${health === "ok" ? "bg-brand" : "bg-risk-high"}`}
          />
          <span className="text-sm font-mono text-ink-muted">{health}</span>
        </div>
        <p className="text-xs text-ink-faint mt-3">
          Change it via the <code className="font-mono">NEXT_PUBLIC_API_BASE</code>{" "}
          environment variable at build/deploy time.
        </p>
      </Card>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}>
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <p className="font-display text-lg">Session Defaults</p>
          {saving ? (
            <Loader2 size={15} className="animate-spin text-ink-faint" />
          ) : savedAt ? (
            <span className="flex items-center gap-1 text-[11px] text-brand font-mono">
              <Check size={13} /> Saved
            </span>
          ) : null}
        </div>
        <p className="text-sm text-ink-muted mb-4">
          Applied automatically when you start a new session from Live Analysis, unless you
          override a field on that request.
        </p>

        {error && (
          <div className="rounded-control border border-risk-high/30 bg-risk-high/5 px-3 py-2 text-xs text-risk-high mb-4">
            {error}
          </div>
        )}

        {!defaults ? (
          <p className="text-sm text-ink-faint font-mono">Loading…</p>
        ) : (
          <div className="divide-y divide-border">
            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm text-ink">Default Camera</p>
                <p className="text-[11px] text-ink-faint mt-0.5">USB index — 0 is usually the built-in webcam</p>
              </div>
              <div className="h-16 w-36 relative">
                <OptionWheel
                  items={["Camera 0", "Camera 1", "Camera 2", "Camera 3", "Camera 4"]}
                  defaultSelected={defaults.camera_id}
                  side="right"
                  fontSize={1.05}
                  spacing={1.25}
                  tilt={12}
                  inset={8}
                  smoothing={180}
                  onChange={(index) => patch({ camera_id: index })}
                />
              </div>
            </div>

            <ToggleRow
              label="Voice Feedback"
              checked={defaults.voice_enabled}
              onChange={(v) => patch({ voice_enabled: v })}
            />
            <ToggleRow
              label="Arduino Laser"
              checked={defaults.arduino_enabled}
              onChange={(v) => patch({ arduino_enabled: v })}
            />

            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm text-ink">Pose Model Complexity</p>
                <p className="text-[11px] text-ink-faint mt-0.5">Scroll, drag, or use arrow keys</p>
              </div>
              <div className="h-16 w-32 relative">
                <OptionWheel
                  items={["Lite", "Full", "Heavy"]}
                  defaultSelected={defaults.model_complexity}
                  side="right"
                  fontSize={1.15}
                  spacing={1.3}
                  tilt={14}
                  inset={8}
                  smoothing={180}
                  onChange={(index) => patch({ model_complexity: index })}
                />
              </div>
            </div>

            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm text-ink">Process Every N Frames</p>
                <p className="text-[11px] text-ink-faint mt-0.5">Higher = faster, lower CPU load</p>
              </div>
              <div className="h-16 w-32 relative">
                <OptionWheel
                  items={["1", "2", "3", "4", "5"]}
                  defaultSelected={defaults.process_every_n - 1}
                  side="right"
                  fontSize={1.15}
                  spacing={1.25}
                  tilt={12}
                  inset={8}
                  smoothing={180}
                  onChange={(index) => patch({ process_every_n: index + 1 })}
                />
              </div>
            </div>
          </div>
        )}
      </Card>
      </motion.div>
    </div>
  );
}
