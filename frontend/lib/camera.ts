// Camera auto-detect. The default path asks the person nothing: try the last
// camera that worked, then indexes 0-3, and keep the first one that actually
// sends video. The backend's start endpoint already refuses (400) a camera
// that opens but sends no frames, so a successful start means "camera found".
import { api, ApiError } from "./api";

const LAST_KEY = "lg.camera.last";
const PIN_KEY = "lg.camera.pin"; // "auto" (default) or a fixed index - advanced fallback
export const CAMERA_CANDIDATES = [0, 1, 2, 3];

function read(key: string): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // private mode: auto-detect still works, it just can't remember
  }
}

/** null = automatic (default). A number = pinned from Settings > Advanced. */
export function getCameraPin(): number | null {
  const v = read(PIN_KEY);
  return v !== null && /^\d+$/.test(v) ? Number(v) : null;
}
export function setCameraPin(index: number | null) {
  write(PIN_KEY, index === null ? null : String(index));
}
export function getLastCamera(): number | null {
  const v = read(LAST_KEY);
  return v !== null && /^\d+$/.test(v) ? Number(v) : null;
}

function isCameraProblem(e: unknown): boolean {
  return e instanceof ApiError && e.status === 400 && /camera|video/i.test(e.message);
}

export const NO_CAMERA_MESSAGE =
  "No camera found. Plug in the webcam, close any app that might be using it (Zoom, Teams, the Camera app, or a browser tab on Register), then press Start again.";

/**
 * Start a session on the first camera that sends video.
 * onTrying(index, attempt, total) lets the UI say what it's doing.
 * Returns the session id and the camera index that worked.
 */
export async function startWithCamera(
  onTrying?: (index: number, attempt: number, total: number) => void
): Promise<{ sessionId: string; camera: number }> {
  const pin = getCameraPin();
  const last = getLastCamera();
  const order =
    pin !== null ? [pin] : Array.from(new Set([...(last !== null ? [last] : []), ...CAMERA_CANDIDATES]));

  let lastError: unknown = null;
  for (let i = 0; i < order.length; i++) {
    const index = order[i];
    onTrying?.(index, i + 1, order.length);
    try {
      const res = await api.sessions.start({ camera_id: index, voice_enabled: false }); // the browser speaks (lib/voice.ts)
      write(LAST_KEY, String(index));
      return { sessionId: res.session_id, camera: index };
    } catch (e) {
      // Only a camera problem means "try the next one". Anything else
      // (backend down, engine failed to load) won't be fixed by another index.
      if (!isCameraProblem(e)) throw e;
      lastError = e;
    }
  }
  if (pin !== null) {
    void lastError;
    throw new Error(
      `Camera ${pin} isn't sending video. It's fixed in Settings > Camera - switch it back to Auto, or check that camera is plugged in and free.`
    );
  }
  throw new Error(NO_CAMERA_MESSAGE);
}

export function rememberCamera(index: number) {
  write(LAST_KEY, String(index));
}

/** The other cameras to try, in order, starting after the current one. */
export function otherCameras(current: number): number[] {
  const n = CAMERA_CANDIDATES.length;
  const start = Math.max(0, CAMERA_CANDIDATES.indexOf(current));
  return Array.from({ length: n - 1 }, (_, i) => CAMERA_CANDIDATES[(start + 1 + i) % n]).filter((c) => c !== current);
}
