"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Camera, Check, RotateCcw, ArrowRight, AlertTriangle } from "lucide-react";
import { api, UserRegisterResponse } from "@/lib/api";
import { CaptureRing } from "@/components/register/CaptureRing";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SparklesCore } from "@/components/ui/sparkles";

type Step = "name" | "preview" | "countdown" | "capturing" | "submitting" | "success" | "error";

const CAPTURE_DURATION_MS = 6000;
// 6 s at 250 ms = 24 frames. The backend accepts at most 30 per request
// (LIFTGUARD_MAX_REGISTER_IMAGES) and needs at least 10 with a face.
const CAPTURE_INTERVAL_MS = 250;
const MAX_CAPTURE_FRAMES = 28;
// Downscale before upload: face detection doesn't need 1080p, and smaller
// frames keep the request fast on a laptop.
const CAPTURE_MAX_WIDTH = 640;

export default function RegisterPage() {
  const [step, setStep] = useState<Step>("name");
  const [displayName, setDisplayName] = useState("");
  const [countdown, setCountdown] = useState(3);
  const [progress, setProgress] = useState(0);
  const [sampleCount, setSampleCount] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [result, setResult] = useState<UserRegisterResponse | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const framesRef = useRef<string[]>([]);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => () => stopCamera(), [stopCamera]);

  // Attaches the already-fetched stream to the <video> element once it
  // actually exists in the DOM (it's conditionally rendered based on
  // `step`, so this can't happen inside startCamera() itself — see the
  // comment there).
  useEffect(() => {
    if (
      (step === "preview" || step === "countdown" || step === "capturing") &&
      videoRef.current &&
      streamRef.current &&
      videoRef.current.srcObject !== streamRef.current
    ) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [step]);

  const startCamera = async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setErrorMsg(
        window.isSecureContext
          ? "This browser doesn't support camera access."
          : "Camera access needs a secure connection. If you're opening this from another " +
            "device's IP address (e.g. http://192.168.x.x:3000), browsers block camera access " +
            "there — use https://, or open the app from localhost on the machine running it."
      );
      setStep("error");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 640 }, facingMode: "user" },
      });
      streamRef.current = stream;
      // Don't touch videoRef.current here — the <video> element doesn't
      // exist yet (it's only rendered once step becomes "preview" below),
      // so videoRef.current is still null at this exact point. Attaching
      // the stream is handled by the effect below, which runs after the
      // step change actually mounts the element.
      setStep("preview");
    } catch (e) {
      const name = e instanceof DOMException ? e.name : "";
      const message =
        name === "NotAllowedError"
          ? "Camera permission was denied. Check your browser's site settings and allow camera access."
          : name === "NotFoundError"
            ? "No camera was found on this device."
            : name === "NotReadableError"
              ? "Couldn't access the camera — it may already be in use by another app or browser tab " +
                "(including another LiftGuard AI session's camera, if one is running)."
              : "Couldn't access your camera. Check your browser's camera permission for this site.";
      setErrorMsg(message);
      setStep("error");
    }
  };

  const beginCapture = () => {
    setStep("countdown");
    setCountdown(3);
  };

  useEffect(() => {
    if (step !== "countdown") return;
    if (countdown === 0) {
      setStep("capturing");
      return;
    }
    const t = setTimeout(() => setCountdown((c) => c - 1), 700);
    return () => clearTimeout(t);
  }, [step, countdown]);

  useEffect(() => {
    if (step !== "capturing") return;

    framesRef.current = [];
    setSampleCount(0);
    setProgress(0);

    const startedAt = Date.now();
    const canvas = canvasRef.current;
    const video = videoRef.current;

    const captureFrame = () => {
      if (!canvas || !video || video.videoWidth === 0) return;
      if (framesRef.current.length >= MAX_CAPTURE_FRAMES) return;
      const scale = Math.min(1, CAPTURE_MAX_WIDTH / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      framesRef.current.push(canvas.toDataURL("image/jpeg", 0.85));
      setSampleCount(framesRef.current.length);
    };

    const interval = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      setProgress(Math.min(1, elapsed / CAPTURE_DURATION_MS));
      captureFrame();
      if (elapsed >= CAPTURE_DURATION_MS) {
        clearInterval(interval);
        submitFrames();
      }
    }, CAPTURE_INTERVAL_MS);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const submitFrames = async () => {
    setStep("submitting");
    stopCamera();
    try {
      const res = await api.users.register(displayName.trim(), framesRef.current);
      setResult(res);
      setStep("success");
    } catch (e) {
      const isNetworkError = e instanceof TypeError;
      setErrorMsg(
        isNetworkError
          ? "Couldn't reach the backend. Make sure it's running, and that its CORS settings " +
            "allow this page's origin (see backend/app/core/config.py — LIFTGUARD_CORS_ORIGINS)."
          : e instanceof Error
            ? e.message
            : "Registration failed"
      );
      setStep("error");
    }
  };

  const retry = () => {
    setErrorMsg(null);
    setStep("name");
  };

  return (
    <div className="max-w-md mx-auto">
      {step === "name" && (
        <Card className="p-8 animate-fade-slide-up">
          <p className="font-display text-xl mb-1">Register a new user</p>
          <p className="text-sm text-ink-muted mb-6">
            Enrolls your face for automatic recognition at the start of live sessions — same
            LBPH matching the desktop app uses, captured here instead of at the camera rig.
          </p>
          <label className="text-[11px] font-mono uppercase tracking-wider text-ink-faint">
            Display Name
          </label>
          <input
            autoFocus
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && displayName.trim() && startCamera()}
            placeholder="Jordan Lee"
            className="mt-2 w-full bg-panel-raised border border-border rounded-control px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:border-brand/40"
          />
          <Button variant="primary" onClick={startCamera} disabled={!displayName.trim()} className="mt-5 w-full justify-center">
            <Camera size={16} /> Continue to Camera
          </Button>
        </Card>
      )}

      {(step === "preview" || step === "countdown" || step === "capturing") && (
        <Card className="p-8 flex flex-col items-center animate-fade-slide-up">
          <div className="relative w-80 h-80 rounded-full overflow-hidden glass-panel-raised scan-surface">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className="w-full h-full object-cover -scale-x-100"
            />
            {step === "countdown" && (
              <div className="absolute inset-0 grid place-items-center bg-void/50">
                <span className="font-display text-6xl text-brand tabular">{countdown || "Go"}</span>
              </div>
            )}
            {step === "capturing" && <CaptureRing progress={progress} sampleCount={sampleCount} size={320} />}
          </div>

          <p className="mt-6 text-sm text-ink-muted text-center max-w-xs">
            {step === "preview" &&
              "Center your face in the frame, then start capture. Slowly turn your head left and right once it begins."}
            {step === "countdown" && "Get ready…"}
            {step === "capturing" && "Hold steady — capturing samples"}
          </p>

          {step === "preview" && (
            <Button variant="primary" size="lg" onClick={beginCapture} className="mt-6">
              Start Capture <ArrowRight size={15} />
            </Button>
          )}
        </Card>
      )}

      {step === "submitting" && (
        <Card className="p-10 flex flex-col items-center gap-4 animate-fade-slide-up">
          <div className="w-10 h-10 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
          <p className="text-sm text-ink-muted font-mono">Processing face samples…</p>
        </Card>
      )}

      {step === "success" && result && (
        <Card className="p-10 flex flex-col items-center gap-4 text-center animate-fade-slide-up relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none">
            <SparklesCore
              background="transparent"
              minSize={0.3}
              maxSize={1}
              particleDensity={70}
              particleColor="#7C5CFF"
              speed={2.5}
              className="w-full h-full"
            />
          </div>
          <div className="relative w-16 h-16 rounded-full bg-brand/10 border border-brand/30 grid place-items-center shadow-glow-brand">
            <Check size={28} className="text-brand" />
          </div>
          <div className="relative">
            <p className="font-display text-xl">{result.display_name} registered</p>
            <p className="text-sm text-ink-muted mt-1">
              {result.samples_used} of {result.frames_received} frames used as face samples
            </p>
          </div>
          <div className="relative flex gap-3 mt-2">
            <Link href="/users">
              <Button variant="secondary">View Users</Button>
            </Link>
            <Link href="/live">
              <Button variant="primary">Start a Session</Button>
            </Link>
          </div>
        </Card>
      )}

      {step === "error" && (
        <Card className="p-8 flex flex-col items-center gap-4 text-center animate-fade-slide-up">
          <AlertTriangle size={28} className="text-risk-high" />
          <p className="text-sm text-ink">{errorMsg}</p>
          <Button variant="secondary" onClick={retry}>
            <RotateCcw size={15} /> Try Again
          </Button>
        </Card>
      )}

      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
}
