// REST client for the LiftGuard AI FastAPI backend.
// Types mirror backend/app/schemas/*.py exactly.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_LIFTGUARD_API_KEY ?? "";

function authHeaders(): HeadersInit {
  return API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {};
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json", ...authHeaders() };
}

export interface SessionStartRequest {
  // "browser": the viewer's own device camera, streamed from the live page.
  camera_id?: number | "browser";
  voice_enabled?: boolean;
  arduino_enabled?: boolean;
  model_complexity?: number;
  process_every_n?: number;
  use_temporal?: boolean;
}

export interface SessionStartResponse {
  session_id: string;
  status: string;
}

export interface SessionReport {
  user: { display_name: string; user_id: number | null; is_guest: boolean } | null;
  exercise: Record<string, unknown>;
  fatigue: Record<string, unknown>;
  peak_risk: number;
  iri_history: number[];
  spine_history: number[];
  using_temporal: boolean;
  using_iri_v2: boolean;
  camera_id: number;
  iri?: Record<string, unknown>;
  uncertainty?: Record<string, unknown>;
}

export interface UserOut {
  user_id: number;
  username: string;
  display_name: string;
  baseline: Record<string, unknown>;
  settings: Record<string, unknown>;
  total_sessions: number;
  last_seen: string | null;
  is_guest: boolean;
}

export interface ArduinoStatus {
  connected: boolean;
  port: string | null;
  laser_on: boolean;
  transport: "usb" | "wifi" | "none";
}

export interface SessionHistoryItem {
  session_id: string;
  display_name: string;
  is_guest: boolean;
  started_at: string | null;
  ended_at: string | null;
  peak_risk: number;
}

export interface SessionDefaults {
  camera_id: number;
  voice_enabled: boolean;
  arduino_enabled: boolean;
  model_complexity: number;
  process_every_n: number;
  use_temporal: boolean;
}

export interface UserRegisterResponse {
  user_id: number;
  display_name: string;
  samples_used: number;
  frames_received: number;
  status: string;
}

/** An API failure whose message is safe to show as-is. */
export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: jsonHeaders(),
      ...options,
    });
  } catch {
    throw new ApiError(
      `Can't reach the LiftGuard backend at ${API_BASE || "this site (proxied)"}. Is it running? Start everything with START-LIFTGUARD.bat (Windows) or ./start.sh.`,
      0
    );
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed?.detail === "string") detail = parsed.detail;
      else if (Array.isArray(parsed?.detail)) detail = parsed.detail.map((d: { msg?: string }) => d.msg).join("; ");
    } catch {
      // not JSON - keep the raw text
    }
    throw new ApiError(detail || `${res.status} ${res.statusText}`, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; app: string }>("/api/health"),

  sessions: {
    start: (body: SessionStartRequest) =>
      request<SessionStartResponse>("/api/sessions/start", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    stop: (sessionId: string) =>
      request<{ status: string }>(`/api/sessions/${sessionId}/stop`, { method: "POST" }),
    report: (sessionId: string) =>
      request<SessionReport>(`/api/sessions/${sessionId}/report`),
    list: () => request<{ active_sessions: string[] }>("/api/sessions"),
    history: (params?: { limit?: number; userId?: number }) => {
      const qs = new URLSearchParams();
      if (params?.limit) qs.set("limit", String(params.limit));
      if (params?.userId) qs.set("user_id", String(params.userId));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request<{ sessions: SessionHistoryItem[] }>(`/api/sessions/history${suffix}`);
    },
    historyReport: (sessionId: string) =>
      request<SessionReport>(`/api/sessions/history/${sessionId}`),
  },

  users: {
    list: () => request<UserOut[]>("/api/users"),
    get: (userId: number) => request<UserOut>(`/api/users/${userId}`),
    register: async (displayName: string, images: string[]): Promise<UserRegisterResponse> => {
      const res = await fetch(`${API_BASE}/api/users/register`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ display_name: displayName, images }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
      }
      return body as UserRegisterResponse;
    },
  },

  hardware: {
    status: (sessionId: string) =>
      request<ArduinoStatus>(`/api/hardware/${sessionId}/status`),
    connect: async (
      sessionId: string,
      transport: "usb" | "wifi",
      opts?: { host?: string; port?: string }
    ): Promise<{ connected: boolean; port: string | null; transport: string; message: string }> => {
      const res = await fetch(`${API_BASE}/api/hardware/${sessionId}/connect`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ transport, host: opts?.host, port: opts?.port }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
      return body;
    },
    disconnect: (sessionId: string) =>
      request<{ connected: boolean; port: string | null; transport: string; message: string }>(
        `/api/hardware/${sessionId}/disconnect`,
        { method: "POST" }
      ),
    calibrate: (sessionId: string) =>
      request<{ status: string }>(`/api/hardware/${sessionId}/calibrate`, { method: "POST" }),
  },

  analytics: {
    iriTimeline: (sessionId: string) =>
      request<{ values: number[] }>(`/api/analytics/${sessionId}/iri-timeline`),
    spineTimeline: (sessionId: string) =>
      request<{ values: number[] }>(`/api/analytics/${sessionId}/spine-timeline`),
    summary: (sessionId: string) =>
      request<SessionReport>(`/api/analytics/${sessionId}/summary`),
    uncertainty: (sessionId: string) =>
      request<Record<string, unknown>>(`/api/analytics/${sessionId}/uncertainty`),
  },

  settings: {
    get: () => request<SessionDefaults>("/api/settings"),
    update: (patch: Partial<SessionDefaults>) =>
      request<SessionDefaults>("/api/settings", {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
  },
};

export { API_BASE, API_KEY };
