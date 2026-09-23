// Opt-in training data ("Help train LiftGuard").
//
// The browser keeps a random contributor id and an on/off switch in
// localStorage. Nothing is saved on the backend unless this id has given
// consent there too (POST /api/contrib/consent, 18+ required). What is
// saved: body points as numbers (shoulders to feet), never video or face
// points. See backend/app/contrib/store.py.
import { API_BASE, ApiError, authHeaders, type ContributionSet, type SessionStartRequest } from "./api";

const ID_KEY = "lg.contrib.id";
const ON_KEY = "lg.contrib.on";
export const CONTRIB_EVENT = "lg-contrib-change";

function store(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function newId(): string {
  const c: Crypto = globalThis.crypto;
  if (typeof c.randomUUID === "function") return c.randomUUID();
  // RFC 4122 v4 from getRandomValues (older WebViews, or plain http)
  const b = c.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function contributorId(): string {
  const s = store();
  let id = s?.getItem(ID_KEY) ?? "";
  if (!UUID_RE.test(id)) {
    id = newId();
    s?.setItem(ID_KEY, id);
  }
  return id;
}

/** Use a code from another device (so its sets can be seen and deleted here). */
export function adoptContributorCode(code: string): boolean {
  const id = code.trim().toLowerCase();
  if (!UUID_RE.test(id)) return false;
  store()?.setItem(ID_KEY, id);
  notify();
  return true;
}

export function contributing(): boolean {
  return store()?.getItem(ON_KEY) === "1";
}

export function setContributing(on: boolean): void {
  const s = store();
  if (on) s?.setItem(ON_KEY, "1");
  else s?.removeItem(ON_KEY);
  notify();
}

function notify() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CONTRIB_EVENT));
}

export function deviceClass(): "phone" | "tablet" | "desktop" | "unknown" {
  if (typeof navigator === "undefined") return "unknown";
  const ua = navigator.userAgent;
  if (/iPad|Tablet/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "tablet";
  if (/Mobi|Android|iPhone/i.test(ua)) return "phone";
  return "desktop";
}

/** Extra /api/sessions/start fields when the switch is on. */
export function contribStartFields(facing?: "environment" | "user"): Partial<SessionStartRequest> {
  if (!contributing()) return {};
  return { contributor_id: contributorId(), device_class: deviceClass(), camera_facing: facing ?? "unknown" };
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/contrib${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Contributor-Id": contributorId(), ...authHeaders() },
    });
  } catch {
    throw new ApiError("Can't reach the LiftGuard backend.", 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(typeof body?.detail === "string" ? body.detail : `${res.status} ${res.statusText}`, res.status);
  }
  return res.json() as Promise<T>;
}

export type Feel = "easy" | "ok" | "hard" | "hurt";

export const contrib = {
  consent: () => call<{ consented: boolean }>("/consent"),
  giveConsent: (adult: boolean) => call<{ consented: boolean }>("/consent", { method: "POST", body: JSON.stringify({ adult }) }),
  list: () => call<{ sets: ContributionSet[] }>(""),
  label: (setId: string, body: { feel?: Feel | null; counting_right?: boolean | null }) =>
    call<ContributionSet>(`/${setId}/label`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (setId: string) => call<{ deleted: string }>(`/${setId}`, { method: "DELETE" }),
  withdraw: () => call<{ deleted_sets: number }>("", { method: "DELETE" }),
};
