"use client";

import { useEffect, useState } from "react";
import { API_BASE, api, SessionDefaults } from "@/lib/api";
import { Alert, Segmented, Spinner, Switch } from "@/components/lg/ui";
import { useBackendOnline } from "@/components/layout/TopNav";
import { CAMERA_CANDIDATES, getCameraPin, getLastCamera, setCameraPin } from "@/lib/camera";

export default function SettingsPage() {
  const online = useBackendOnline();
  const [defaults, setDefaults] = useState<SessionDefaults | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings.get().then(setDefaults).catch((e) => setError(e instanceof Error ? e.message : "Couldn't load settings"));
  }, []);

  // Every change saves on its own; there is no separate Save button.
  const patch = async (fields: Partial<SessionDefaults>) => {
    if (!defaults) return;
    const before = defaults;
    setDefaults({ ...defaults, ...fields }); // optimistic
    setSaving(true);
    setError(null);
    try {
      setDefaults(await api.settings.update(fields));
      setSavedAt(Date.now());
    } catch (e) {
      setDefaults(before); // roll back so the control shows what is really stored
      setError(e instanceof Error ? e.message : "Couldn't save");
    } finally {
      setSaving(false);
    }
  };

  const rows: [string, string, React.ReactNode][] = defaults
    ? [
        ["Movement mode", "Squat is the mode available today. More movements plug in here.", <Segmented key="m" label="Movement mode" options={["Squat"]} value={0} onChange={() => {}} />],
        ["Camera", "Found automatically at start: LiftGuard uses the first camera that sends video.", <CameraSetting key="c" />],
        ["Voice cues", "Spoken feedback during the session.", <Switch key="v" label="Voice cues" checked={defaults.voice_enabled} onChange={(v) => patch({ voice_enabled: v })} />],
        ["Laser pointer", "Arduino pan-tilt laser, if one is plugged in.", <Switch key="l" label="Laser pointer" checked={defaults.arduino_enabled} onChange={(v) => patch({ arduino_enabled: v })} />],
        ["Pose model", "Lite is fastest. Heavy is most accurate.", <Segmented key="p" label="Pose model" options={["Lite", "Full", "Heavy"]} value={defaults.model_complexity} onChange={(i) => patch({ model_complexity: i })} />],
        ["Process every", "Skip frames to save CPU on slower laptops.", <Segmented key="n" label="Process every N frames" options={["1", "2", "3", "4", "5"]} value={defaults.process_every_n - 1} onChange={(i) => patch({ process_every_n: i + 1 })} />],
      ]
    : [];

  return (
    <div className="lg-fade grid gap-10" style={{ gridTemplateColumns: "400px minmax(0,1fr)" }}>
      <div>
        <div className="lg-m lg-dim">Session defaults</div>
        <div className="lg-d mt-2" style={{ fontSize: 120 }}>
          Set once.
          <br />
          Move.
        </div>
        <p className="lg-dim mt-4" style={{ fontSize: 16, lineHeight: 1.45 }}>
          Applied to every new session. Nothing here needs touching mid-movement.
        </p>
        <div className="lg-m mt-6 flex items-center gap-2" style={{ color: saving ? "var(--lg-dim)" : savedAt ? "var(--lg-mint)" : "var(--lg-faint)" }} aria-live="polite">
          {saving ? (
            <>
              <Spinner /> Saving
            </>
          ) : savedAt ? (
            "✓ Saved"
          ) : (
            "Changes save automatically"
          )}
        </div>
        <div className="lg-row mt-8 pt-4">
          <div className="lg-m lg-dim">Backend</div>
          <div className="flex items-center gap-2 mt-2" style={{ fontSize: 15 }}>
            <span className="lg-dot" style={{ background: online ? "var(--lg-mint)" : online === false ? "var(--lg-amber)" : "var(--lg-faint)" }} />
            {online === null ? "Checking" : online ? "Online" : "Offline"} · <span className="lg-dim">{API_BASE || "same origin (proxied)"}</span>
          </div>
          <p className="lg-faint mt-2" style={{ fontSize: 13 }}>
            Set with NEXT_PUBLIC_API_BASE at build time.
          </p>
        </div>
      </div>
      <div>
        {error && <Alert>{error}</Alert>}
        {!defaults && !error
          ? [0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="lg-skel my-6" style={{ height: 52 }} />)
          : rows.map(([a, b, c]) => (
              <div key={a} className="lg-row flex items-center justify-between py-5 gap-6">
                <div>
                  <div className="lg-d" style={{ fontSize: 42 }}>
                    {a}
                  </div>
                  <div className="lg-dim mt-1.5" style={{ fontSize: 14 }}>
                    {b}
                  </div>
                </div>
                {c}
              </div>
            ))}
      </div>
    </div>
  );
}

/** Automatic by default. Picking an index is an advanced fallback, kept out of the way. */
function CameraSetting() {
  const [pin, setPin] = useState<number | null>(null);
  const [last, setLast] = useState<number | null>(null);
  const [advanced, setAdvanced] = useState(false);
  useEffect(() => {
    const p = getCameraPin();
    setPin(p);
    setLast(getLastCamera());
    setAdvanced(p !== null);
  }, []);
  const choose = (p: number | null) => {
    setCameraPin(p);
    setPin(p);
  };
  return (
    <div className="flex flex-col items-end gap-2">
      <div className="lg-m" style={{ color: pin === null ? "var(--lg-mint)" : "var(--lg-amber)" }}>
        {pin === null ? (last !== null ? `Automatic · last found camera ${last}` : "Automatic") : `Fixed to camera ${pin}`}
      </div>
      {advanced ? (
        <div className="flex items-center gap-3">
          <Segmented
            label="Camera"
            options={["Auto", ...CAMERA_CANDIDATES.map(String)]}
            value={pin === null ? 0 : CAMERA_CANDIDATES.indexOf(pin) + 1}
            onChange={(i) => choose(i === 0 ? null : CAMERA_CANDIDATES[i - 1])}
          />
        </div>
      ) : (
        <button className="lg-m lg-faint underline" style={{ fontSize: 11 }} onClick={() => setAdvanced(true)}>
          Advanced: pick a camera by number
        </button>
      )}
    </div>
  );
}
