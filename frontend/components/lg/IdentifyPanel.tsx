"use client";

import { useEffect, useRef, useState } from "react";
import { api, FaceIdentifyResponse } from "@/lib/api";
import { Spinner } from "@/components/lg/ui";

// On-demand "who's in front of the camera?". Grabs 6 frames over ~1.5 s from
// this browser's camera, sends them to the backend on this same computer,
// and drops them. Only rendered when the backend says this browser is local.
const FRAMES = 6;
const INTERVAL_MS = 250;

export default function IdentifyPanel() {
  const [state, setState] = useState<"idle" | "camera" | "checking" | "done" | "error">("idle");
  const [result, setResult] = useState<FaceIdentifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stop = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };
  useEffect(() => () => stop(), []);

  const run = async () => {
    setError(null);
    setResult(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
      streamRef.current = stream;
      setState("camera");
      await new Promise((r) => setTimeout(r, 50));
      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play().catch(() => undefined);
      await new Promise((r) => setTimeout(r, 700)); // let exposure settle
      const canvas = document.createElement("canvas");
      const frames: string[] = [];
      for (let i = 0; i < FRAMES; i++) {
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);
        frames.push(canvas.toDataURL("image/jpeg", 0.85));
        await new Promise((r) => setTimeout(r, INTERVAL_MS));
      }
      stop();
      setState("checking");
      setResult(await api.users.identify(frames));
      frames.length = 0;
      setState("done");
    } catch (e) {
      stop();
      setError(e instanceof Error ? e.message : "Couldn't identify");
      setState("error");
    }
  };

  const reasonText: Record<string, string> = {
    no_face: "No clear face in view. Face the camera in good light and try again.",
    no_match: "Not recognised. This face doesn't match anyone enrolled on this computer.",
    ambiguous: "Looks like more than one enrolled person. Try again with only one face in view.",
  };

  return (
    <div className="lg-card" data-testid="identify-panel">
      <div className="lg-m lg-dim">Who&apos;s training?</div>
      <div className="flex items-center gap-4 mt-3">
        <button className="lg-btn" onClick={run} disabled={state === "camera" || state === "checking"}>
          {state === "camera" ? "Looking…" : state === "checking" ? <><Spinner /> Checking</> : "Identify me"}
        </button>
        <span className="lg-m" style={{ color: "var(--lg-mint)", fontSize: 12 }}>Your face never leaves this device</span>
      </div>
      {state === "camera" && (
        <video ref={videoRef} muted playsInline className="mt-3 rounded-lg -scale-x-100" style={{ width: 240, background: "#0b0b0c" }} />
      )}
      {state === "done" && result && (
        <div className="mt-3" style={{ fontSize: 18 }}>
          {result.matched && result.user ? (
            <span data-testid="identify-result">
              It&apos;s <b>{result.user.display_name}</b>
            </span>
          ) : (
            <span className="lg-dim" data-testid="identify-result">{reasonText[result.reason ?? "no_match"]}</span>
          )}
        </div>
      )}
      {state === "error" && error && <div className="lg-alert mt-3" style={{ fontSize: 14 }}>{error}</div>}
    </div>
  );
}
