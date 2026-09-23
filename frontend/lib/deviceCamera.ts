// The viewer's own device camera as the analysis source.
//
// The live page opens the camera with getUserMedia and sends JPEG frames
// over the /ws/live socket; the backend analyses them and sends frames with
// the pose overlay back, exactly like a camera plugged into the backend.
// This is what makes a real camera work through a hosted link.
import { useEffect } from "react";

// Big enough for pose detection at 3 m, small enough to keep a phone on
// mobile data and a 2-core server ahead of the stream.
const WIDTH = 640;
const HEIGHT = 360;
const SEND_EVERY_MS = 100; // ~10 fps offered; the backend keeps only the newest
const JPEG_QUALITY = 0.7;

export async function openDeviceCamera(): Promise<MediaStream> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error(
      window.isSecureContext
        ? "This browser can't use a camera."
        : "The browser only allows the camera on https:// or localhost. Open LiftGuard through its https link."
    );
  }
  try {
    return await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
      audio: false,
    });
  } catch (e) {
    const name = e instanceof DOMException ? e.name : "";
    if (name === "NotAllowedError" || name === "SecurityError")
      throw new Error("Camera access was blocked. Allow the camera for this site in the browser's address bar, then press Start again.");
    if (name === "NotFoundError" || name === "OverconstrainedError")
      throw new Error("No camera found on this device.");
    if (name === "NotReadableError")
      throw new Error("The camera is in use by another app or tab. Close it, then press Start again.");
    throw new Error(`Couldn't open this device's camera. ${e instanceof Error ? e.message : ""}`.trim());
  }
}

export function stopDeviceCamera(stream: MediaStream | null) {
  stream?.getTracks().forEach((t) => t.stop());
}

/** While `stream` and a session are live, send its frames with `send` (base64 JPEG). */
export function useFrameUplink(stream: MediaStream | null, send: (jpegBase64: string) => boolean, enabled: boolean) {
  useEffect(() => {
    if (!stream || !enabled) return;
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.srcObject = stream;
    void video.play().catch(() => {});
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    let busy = false;
    const timer = window.setInterval(() => {
      if (busy || !ctx || video.readyState < 2 || !video.videoWidth) return;
      // Keep the camera's aspect ratio inside 640x360.
      const scale = Math.min(WIDTH / video.videoWidth, HEIGHT / video.videoHeight, 1);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      busy = true;
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            busy = false;
            return;
          }
          const reader = new FileReader();
          reader.onloadend = () => {
            busy = false;
            const url = String(reader.result ?? "");
            const comma = url.indexOf(",");
            if (comma > 0) send(url.slice(comma + 1));
          };
          reader.readAsDataURL(blob);
        },
        "image/jpeg",
        JPEG_QUALITY
      );
    }, SEND_EVERY_MS);
    return () => {
      window.clearInterval(timer);
      video.srcObject = null;
    };
  }, [stream, send, enabled]);
}
