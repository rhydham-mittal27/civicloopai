import type {
  Analysis,
  CityOption,
  Fix,
  Incident,
  IncidentStatus,
  MediaAsset,
  Me,
  ReporterType,
  UploadFile,
  Vehicle,
  Verification,
  RoutePlan,
  WorkOrder,
  WorkOrderStatus,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiConfig {
  /** Server address without a path, for example http://192.168.1.20:8000 */
  baseUrl: () => string;
  getToken: () => string | null | Promise<string | null>;
  /** Called when the server says the sign-in is no longer valid (401). */
  onUnauthorized?: () => void;
  fetch?: typeof fetch;
  /** Milliseconds before a request is given up on. Uploads get four times as long. */
  timeoutMs?: number;
}

/** The server's error text, from either a plain message or a list of validation problems. */
export function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const text = detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : ""))
        .filter(Boolean)
        .join(". ");
      if (text) return text;
    }
  }
  return fallback;
}

export function normaliseServerUrl(input: string): string {
  const trimmed = input.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
}

const query = (params: Record<string, string | number | undefined>) => {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
};

export function createApi(config: ApiConfig) {
  const doFetch = config.fetch ?? fetch;
  const timeout = config.timeoutMs ?? 20_000;
  const root = () => `${normaliseServerUrl(config.baseUrl())}/api/v1`;

  async function authHeaders(): Promise<Record<string, string>> {
    const token = await config.getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function request<T>(path: string, init: RequestInit & { upload?: boolean } = {}): Promise<T> {
    const base = normaliseServerUrl(config.baseUrl());
    if (!base) throw new ApiError("Set the server address first.", 0);
    const headers: Record<string, string> = { Accept: "application/json", ...(await authHeaders()), ...((init.headers as Record<string, string> | undefined) ?? {}) };
    if (init.body && typeof init.body === "string") headers["Content-Type"] = "application/json";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), init.upload ? timeout * 4 : timeout);
    let response: Response;
    try {
      response = await doFetch(`${root()}${path}`, { ...init, headers, signal: controller.signal });
    } catch (error) {
      const aborted = error instanceof Error && error.name === "AbortError";
      throw new ApiError(aborted ? "The server took too long to answer. Try again." : "Cannot reach the server. Check your connection and the server address.", 0);
    } finally {
      clearTimeout(timer);
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401 && (await config.getToken())) config.onUnauthorized?.();
      throw new ApiError(messageFrom(body, `Request failed (${response.status})`), response.status);
    }
    return body as T;
  }

  const post = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

  /**
   * Sends a photo. In a browser the picked file is fetched into a real Blob. On a phone the file stays where it is and
   * React Native's own XMLHttpRequest streams it from there: the global fetch on current Expo versions does not understand a
   * {uri, name, type} file entry, which is why photos silently failed to upload.
   */
  async function upload<T>(path: string, file: UploadFile, fields: Record<string, string> = {}) {
    const form = new FormData();
    const onPhone = typeof navigator !== "undefined" && navigator.product === "ReactNative";
    if (!onPhone && typeof document !== "undefined") {
      const blob = await (await fetch(file.uri)).blob();
      form.append("file", blob, file.name);
    } else {
      form.append("file", file as unknown as Blob);
    }
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    if (!onPhone) return request<T>(path, { method: "POST", body: form, upload: true });

    const base = normaliseServerUrl(config.baseUrl());
    if (!base) throw new ApiError("Set the server address first.", 0);
    const auth = await authHeaders();
    return new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${root()}${path}`);
      xhr.setRequestHeader("Accept", "application/json");
      if (auth.Authorization) xhr.setRequestHeader("Authorization", auth.Authorization);
      xhr.timeout = timeout * 4;
      xhr.onload = async () => {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* not JSON */
        }
        if (xhr.status >= 200 && xhr.status < 300) return resolve(body as T);
        if (xhr.status === 401 && (await config.getToken())) config.onUnauthorized?.();
        reject(new ApiError(messageFrom(body, `Request failed (${xhr.status})`), xhr.status));
      };
      xhr.onerror = () => reject(new ApiError("Cannot reach the server. Check your connection and the server address.", 0));
      xhr.ontimeout = () => reject(new ApiError("The server took too long to answer. Try again.", 0));
      xhr.send(form);
    });
  }

  return {
    /** Where an image is fetched from. The Image component needs the headers from `authHeaders()` too. */
    mediaUrl: (assetId: string) => `${root()}/media/${assetId}/content`,
    authHeaders,

    // server and identity
    ping: async () => {
      const base = normaliseServerUrl(config.baseUrl());
      if (!base) throw new ApiError("Set the server address first.", 0);
      try {
        const response = await doFetch(`${base}/health`);
        return response.ok;
      } catch {
        return false;
      }
    },
    login: (email: string, password: string) => post<{ access_token: string }>("/auth/login", { email, password }),
    register: (input: { name: string; email: string; password: string; city: string; pincode: string }) =>
      post<{ user_id: string; email: string; role: string; city: string; pincode: string; city_verified: boolean }>("/auth/register", input),
    cities: (q: string) => request<CityOption[]>(`/tenants${query({ q })}`),
    me: () => request<Me>("/auth/me"),

    // incidents
    listIncidents: (status?: IncidentStatus, limit = 100) => request<Incident[]>(`/incidents${query({ status_filter: status, limit })}`),
    getIncident: (id: string) => request<Incident>(`/incidents/${id}`),
    createIncident: (input: {
      reporter_type: ReporterType;
      description: string;
      latitude: number;
      longitude: number;
      occurred_at: string;
      pincode?: string;
    }, idempotencyKey?: string) =>
      request<Incident>("/incidents", { method: "POST", body: JSON.stringify(input), headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined }),
    listMedia: (id: string) => request<MediaAsset[]>(`/incidents/${id}/media`),
    uploadMedia: (id: string, file: UploadFile) => upload<MediaAsset>(`/incidents/${id}/media`, file),
    getAnalysis: (id: string) => request<Analysis | null>(`/incidents/${id}/analysis`),

    // crew
    listOrders: (status?: WorkOrderStatus) => request<WorkOrder[]>(`/work-orders${query({ status })}`),
    myRoutes: () => request<RoutePlan[]>("/routes/mine"),
    getRoute: (id: string) => request<RoutePlan>(`/routes/${id}`),
    getOrder: (id: string) => request<WorkOrder>(`/work-orders/${id}`),
    startOrder: (id: string) => post<WorkOrder>(`/work-orders/${id}/start`),
    completeOrder: (id: string) => post<WorkOrder>(`/work-orders/${id}/complete`),
    submitEvidence: (incidentId: string, file: UploadFile, notes?: string) =>
      upload<Verification>(`/incidents/${incidentId}/verification`, file, notes ? { notes } : {}),
    getVerification: (incidentId: string) => request<Verification | null>(`/incidents/${incidentId}/verification`),

    // vehicle location
    myVehicles: () => request<Vehicle[]>("/vehicles/mine"),
    sharePosition: (vehicleId: string, fix: Fix) => post<{ accepted: number; dropped: number }>(`/vehicles/${vehicleId}/position`, fix),
  };
}

export type Api = ReturnType<typeof createApi>;
