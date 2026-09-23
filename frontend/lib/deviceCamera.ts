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

export type Facing = "user" | "environment";

const FACING_KEY = "liftguard.deviceFacing";

/** Phones and tablets film the lifter with the back camera; laptops only have the front one. */
export function isMobileDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  const uaData = (navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData;
  if (uaData && typeof uaData.mobile === "boolean") return uaData.mobile;
  if (/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)) return true;
  // iPadOS reports itself as a Mac; it is the only "Mac" with a touch screen.
  return /Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1;
}

/** The camera to open first: the one picked last time, else back on mobile, front elsewhere. */
export function defaultFacing(): Facing {
  try {
    const saved = window.localStorage.getItem(FACING_KEY);
    if (saved === "user" || saved === "environment") return saved;
  } catch {
    /* private mode */
  }
  return isMobileDevice() ? "environment" : "user";
}

export function rememberFacing(facing: Facing) {
  try {
    window.localStorage.setItem(FACING_KEY, facing);
  } catch {
    /* private mode */
  }
}

/** Which way the stream's camera faces, when the browser says (phones do; most laptops don't). */
export function streamFacing(stream: MediaStream | null): Facing | null {
  const f = stream?.getVideoTracks()[0]?.getSettings().facingMode;
  return f === "user" || f === "environment" ? f : null;
}

function streamDeviceId(stream: MediaStream | null): string {
  return stream?.getVideoTracks()[0]?.getSettings().deviceId ?? "";
}

/** How many cameras this device has. Labels and IDs only appear after permission. */
export async function countVideoInputs(): Promise<number> {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((d) => d.kind === "videoinput").length;
  } catch {
    return 0;
  }
}

type Choice = { facing: Facing } | { deviceId: string };

export async function openDeviceCamera(choice: Choice = { facing: defaultFacing() }): Promise<MediaStream> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error(
      window.isSecureContext
        ? "This browser can't use a camera."
        : "The browser only allows the camera on https:// or localhost. Open LiftGuard through its https link."
    );
  }
  // "ideal", not "exact": a laptop with only a front camera still opens it
  // instead of failing.
  const pick = "deviceId" in choice ? { deviceId: { exact: choice.deviceId } } : { facingMode: { ideal: choice.facing } };
  try {
    return await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, ...pick },
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

/**
 * Switch to this device's other camera (back <-> front). Stops the current
 * stream first, because many phones can't run two cameras at once. Tries
 * the opposite facingMode; if the browser hands back the same camera (common
 * on laptops and some Androids), steps to the next camera by device ID.
 * If nothing else opens, reopens the camera it started on and throws.
 */
export async function flipDeviceCamera(current: MediaStream, currentFacing: Facing): Promise<{ stream: MediaStream; facing: Facing }> {
  const oldId = streamDeviceId(current);
  const target: Facing = currentFacing === "environment" ? "user" : "environment";
  stopDeviceCamera(current);
  let next: MediaStream | null = null;
  try {
    next = await openDeviceCamera({ facing: target });
  } catch {
    next = null;
  }
  if (next && oldId && streamDeviceId(next) === oldId) {
    const cams = (await navigator.mediaDevices.enumerateDevices().catch(() => [] as MediaDeviceInfo[])).filter((d) => d.kind === "videoinput" && d.deviceId);
    const i = cams.findIndex((d) => d.deviceId === oldId);
    const other = cams.length > 1 ? cams[(i + 1) % cams.length] : undefined;
    if (other && other.deviceId !== oldId) {
      stopDeviceCamera(next);
      next = await openDeviceCamera({ deviceId: other.deviceId }).catch(() => null);
    } else {
      stopDeviceCamera(next);
      next = null;
    }
  }
  if (!next) {
    const back = await openDeviceCamera(oldId ? { deviceId: oldId } : { facing: currentFacing });
    const err = new Error("No other camera on this device.") as Error & { stream?: MediaStream };
    err.stream = back;
    throw err;
  }
  return { stream: next, facing: streamFacing(next) ?? target };
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
