"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, FaceStatus, UserRegisterResponse } from "@/lib/api";
import { Spinner } from "@/components/lg/ui";

type Step = "name" | "preview" | "countdown" | "capturing" | "submitting" | "success" | "error";

const CAPTURE_DURATION_MS = 6000;
// 6 s at 250 ms = 24 frames. The backend accepts at most 30 per request
// (LIFTGUARD_MAX_REGISTER_IMAGES) and needs at least 5 with one clear face.
const CAPTURE_INTERVAL_MS = 250;
const MAX_CAPTURE_FRAMES = 28;
// Downscale before upload: face detection doesn't need 1080p, and smaller
// frames keep the request fast on a laptop.
const CAPTURE_MAX_WIDTH = 640;

// Honest privacy copy. Shown only when the backend confirms this browser is on
// the same computer, which is when it is true.
const FACE_PRIVACY_COPY =
  "Your face never leaves this device. LiftGuard keeps a face signature (128 numbers), not a photo, on this computer only. It is never uploaded or shared, and you can delete it on the Users page.";

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterInner />
    </Suspense>
  );
}

function RegisterInner() {
  const params = useSearchParams();
  // /register?user=12 re-enrolls an existing user's face.
  const reenrollId = params.get("user") ? Number(params.get("user")) : null;
  const [faceStatus, setFaceStatus] = useState<FaceStatus | null>(null);
  const [faceStatusError, setFaceStatusError] = useState<string | null>(null);
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

  useEffect(() => {
    api.users
      .faceStatus()
      .then(setFaceStatus)
      .catch((e) => setFaceStatusError(e instanceof Error ? e.message : "Couldn't check face ID"));
    if (reenrollId) {
      api.users
        .get(reenrollId)
        .then((u) => setDisplayName(u.display_name))
        .catch(() => setFaceStatusError("That user wasn't found."));
    }
  }, [reenrollId]);

  const faceReady = !!faceStatus && faceStatus.available && faceStatus.local;

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
      let res: UserRegisterResponse;
      if (reenrollId) {
        const u = await api.users.enrollFace(reenrollId, framesRef.current);
        res = { user_id: u.user_id, display_name: u.display_name, samples_used: framesRef.current.length, frames_received: framesRef.current.length, status: "enrolled" };
      } else {
        res = await api.users.register(displayName.trim(), framesRef.current);
      }
      framesRef.current = [];
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
      framesRef.current = [];
      setStep("error");
    }
  };

  const retry = () => {
    setErrorMsg(null);
    setStep("name");
  };

  const cancel = () => {
    stopCamera();
    setErrorMsg(null);
    setStep("name");
  };

  // Esc backs out of the camera steps.
  useEffect(() => {
    if (step !== "preview" && step !== "countdown") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const expectedFrames = Math.floor(CAPTURE_DURATION_MS / CAPTURE_INTERVAL_MS);
  const onCamera = step === "preview" || step === "countdown" || step === "capturing";
  const frameColor =
    step === "success" ? "var(--lg-mint)" : step === "error" ? "var(--lg-amber)" : step === "capturing" ? "var(--lg-ink)" : "var(--lg-line)";

  return (
    <div className="lg-fade">
      {step === "name" ? (
        <div className="max-w-3xl">
          <div className="lg-m lg-dim">{reenrollId ? "Set up face ID" : "Register someone"}</div>
          <div className="lg-d mt-1.5" style={{ fontSize: 92 }}>
            {reenrollId ? displayName || "…" : <>Who&apos;s registering?</>}
          </div>
          <p className="lg-dim mt-3" style={{ fontSize: 16, maxWidth: 560 }}>
            Enrolls a face so LiftGuard recognises this person when a session starts on this computer&apos;s camera. About 6 seconds in front of the webcam.
          </p>
          {faceReady && (
            <p className="lg-chip lg-m mt-4" data-testid="face-privacy" style={{ color: "var(--lg-mint)", borderColor: "var(--lg-mint)", whiteSpace: "normal", maxWidth: 620, lineHeight: 1.5 }}>
              {FACE_PRIVACY_COPY}
            </p>
          )}
          {faceStatus && !faceStatus.local && (
            <div className="lg-alert mt-4" style={{ fontSize: 15, maxWidth: 620 }}>
              Face ID is not available from this device. It only runs in a browser on the computer that runs LiftGuard, so faces never travel over the network. Open LiftGuard on that computer (http://localhost:3000) to register.
            </div>
          )}
          {faceStatus && faceStatus.local && !faceStatus.available && (
            <div className="lg-alert mt-4" style={{ fontSize: 15, maxWidth: 620 }}>
              Face ID is not available on this machine: the face model files are missing. Run <code>python fetch_face_models.py</code> in backend/, then restart LiftGuard.
            </div>
          )}
          {faceStatusError && <div className="lg-alert mt-4" style={{ fontSize: 15, maxWidth: 620 }}>{faceStatusError}</div>}
          <input
            autoFocus
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && displayName.trim() && faceReady && startCamera()}
            disabled={!!reenrollId}
            placeholder="Jordan Lee"
            aria-label="Display name"
            className="lg-input lg-d mt-8"
            style={{ fontSize: 72 }}
          />
          <button className="lg-btn lg mt-8" onClick={startCamera} disabled={!displayName.trim() || !faceReady}>
            Continue to camera <kbd>Enter</kbd>
          </button>
        </div>
      ) : (
        <div className="grid gap-7" style={{ gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1fr)", minHeight: "calc(100vh - 150px)" }}>
          <div className="relative rounded-[18px] overflow-hidden" style={{ background: "#0b0b0c", boxShadow: `inset 0 0 0 6px ${frameColor}`, transition: "box-shadow .2s ease" }}>
            {onCamera && <video ref={videoRef} autoPlay muted playsInline className="absolute inset-0 w-full h-full object-cover -scale-x-100" style={{ padding: 6, borderRadius: 18 }} />}
            {onCamera && (
              <div
                className="absolute left-1/2 top-[45%] -translate-x-1/2 -translate-y-1/2 pointer-events-none"
                style={{ width: 280, height: 360, borderRadius: "50%", border: `4px solid ${step === "capturing" ? "var(--lg-ink)" : "rgba(244,243,238,.35)"}` }}
              />
            )}
            {step === "countdown" && (
              <div className="absolute inset-0 grid place-items-center" style={{ background: "rgba(0,0,0,.45)" }}>
                <span className="lg-d" style={{ fontSize: 260 }}>
                  {countdown || "Go"}
                </span>
              </div>
            )}
            {step === "capturing" && (
              <div className="absolute left-0 right-0 bottom-0" style={{ height: 10, background: "rgba(0,0,0,.5)" }}>
                <div style={{ height: "100%", width: `${progress * 100}%`, background: "var(--lg-ink)", transition: "width .25s linear" }} />
              </div>
            )}
            {(step === "submitting" || step === "success" || step === "error") && (
              <div className="absolute inset-0 grid place-items-center">
                <span className="lg-d" style={{ fontSize: 140, color: frameColor }}>
                  {step === "submitting" ? "…" : step === "success" ? "✓" : "!"}
                </span>
              </div>
            )}
            <span className="lg-chip lg-m absolute left-6 top-6" style={{ background: "rgba(0,0,0,.45)", color: "var(--lg-ink)" }}>
              {step === "preview" ? "Centre your face in the oval" : step === "countdown" ? "Get ready" : step === "capturing" ? "Capturing · turn your head slowly" : step === "submitting" ? "Checking the samples" : step === "success" ? "Enrolled" : "Didn't work"}
            </span>
          </div>

          <div className="flex flex-col">
            <div className="lg-m lg-dim">{step === "success" ? "Registered" : "Registering"}</div>
            <div className="lg-d mt-1.5" style={{ fontSize: 88 }}>
              {(result?.display_name ?? displayName).trim() || "—"}
            </div>

            {step === "success" && result ? (
              <>
                <div className="lg-d mt-8" style={{ fontSize: 200, color: "var(--lg-mint)" }}>
                  {result.samples_used}
                  <span style={{ color: "var(--lg-faint)" }}>/{result.frames_received}</span>
                </div>
                <div className="lg-m lg-dim mt-3">Frames used for the face signature · the frames themselves were discarded</div>
                <div className="flex gap-3 mt-auto pt-8">
                  <Link href="/live" className="lg-btn lg">
                    Start a session
                  </Link>
                  <Link href="/users" className="lg-btn g lg">
                    See everyone
                  </Link>
                </div>
              </>
            ) : step === "error" ? (
              <>
                <div className="lg-alert mt-8" style={{ fontSize: 16 }}>
                  {errorMsg}
                </div>
                <div className="flex gap-3 mt-auto pt-8">
                  <button className="lg-btn lg" onClick={retry}>
                    Try again
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="lg-d mt-8" style={{ fontSize: 200, color: step === "capturing" ? "var(--lg-ink)" : "var(--lg-faint)" }}>
                  {sampleCount}
                  <span style={{ color: "var(--lg-faint)" }}>/{expectedFrames}</span>
                </div>
                <div className="lg-m lg-dim mt-3">Frames captured · needs at least 5 with one clear face · frames are discarded after</div>
                <div className="lg-m mt-3" style={{ color: "var(--lg-mint)" }}>Your face never leaves this device</div>
                {step === "submitting" && (
                  <div className="lg-m mt-6 flex items-center gap-2.5">
                    <Spinner /> Making the face signature
                  </div>
                )}
                <div className="flex gap-3 mt-auto pt-8">
                  {step === "preview" && (
                    <button className="lg-btn lg" onClick={beginCapture}>
                      Start capture
                    </button>
                  )}
                  {(step === "preview" || step === "countdown") && (
                    <button className="lg-btn g lg" onClick={cancel}>
                      Cancel <kbd>Esc</kbd>
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
}
