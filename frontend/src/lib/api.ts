export type Role = "reporter" | "supervisor" | "sanitation_worker" | "admin";

export type IncidentStatus =
  | "pending_analysis"
  | "ready_for_review"
  | "approved"
  | "in_progress"
  | "resolved"
  | "verified"
  | "uncertain"
  | "rejected";

export type ReporterType = "resident" | "field_worker" | "supervisor";
export type WorkOrderStatus = "draft" | "approved" | "assigned" | "in_progress" | "completed" | "cancelled";
export type VerificationStatus = "pending" | "verified" | "uncertain" | "rejected";

export interface Incident {
  id: string;
  reporter_id: string | null;
  reporter_type: ReporterType;
  description: string;
  latitude: number;
  longitude: number;
  pincode: string | null;
  occurred_at: string;
  status: IncidentStatus;
}

export interface MediaAsset {
  id: string;
  storage_key: string;
  content_type: string;
  sha256: string;
  is_after_cleanup: boolean;
}

export interface Analysis {
  id: string;
  incident_id: string;
  provider: string;
  model_name: string;
  category: string;
  severity: string | null;
  confidence: number | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Risk {
  id: string;
  incident_id: string;
  score: number;
  confidence: number | null;
  factors: Record<string, number>;
  /** "probability": chance of another report within 500 m in 30 days. "formula": a 0-1 index. */
  kind: "probability" | "formula";
  method: string;
  contributions: Record<string, number>;
  model_version: string;
  created_at: string;
}

export interface QueueItem {
  incident: Incident;
  risk: Risk | null;
  work_orders: WorkOrder[];
}

export interface WorkOrder {
  id: string;
  incident_id: string;
  status: WorkOrderStatus;
  priority: number;
  estimated_volume: number | null;
  override_reason: string | null;
  approved_by: string | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  created_at: string;
  incident: Incident | null;
}

export interface Job {
  id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "dead_letter" | "cancelled";
  result: Record<string, unknown> | null;
  attempt_count: number;
  max_attempts?: number;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at?: string;
  completed_at?: string | null;
}

export interface AnalyzeQueued {
  job_id: string;
  status: string;
  detail: string;
}

export interface AnalyzeDone {
  id: string;
  category: string;
  severity: string | null;
  confidence: number | null;
  risk_score: number;
}

export interface DuplicateCandidate {
  incident: Incident;
  similarity_score: number;
  factors: { distance: number; time: number; text: number; category: number };
  text_method: "embedding" | "word-overlap";
  already_grouped: boolean;
}

export interface DuplicateCluster {
  id: string;
  confirmed: boolean;
  created_at: string;
  members: { incident_id: string; similarity_score: number | null; description: string; status: string | null }[];
}

export interface RouteStop {
  sequence: number;
  work_order_id: string;
  planned_volume: number | null;
  priority: number | null;
  incident: Incident | null;
}

export interface RoutePlan {
  id: string;
  solver: string | null;
  greedy_distance_km: number | null;
  /** Positive when the plan is shorter than the nearest-neighbour route. */
  saving_vs_greedy: number | null;
  /** Work-order ids in the order the nearest-neighbour and selection baselines would visit them. */
  greedy_order: string[] | null;
  selection_order: string[] | null;
  /** [latitude, longitude] of the depot, when one was given. */
  depot: [number, number] | null;
  max_duration_minutes: number | null;
  vehicle_capacity: number;
  estimated_distance_km: number | null;
  estimated_duration_minutes: number | null;
  baseline_distance_km: number | null;
  saving_ratio: number | null;
  approved_by: string | null;
  engine_version: string | null;
  created_at: string;
  stops: RouteStop[];
}

export interface Verification {
  id: string;
  incident_id: string;
  status: VerificationStatus;
  evidence_notes: string | null;
  submitted_by: string | null;
  reviewed_by: string | null;
  review_reason: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface TimelineEvent {
  id: string;
  action: string;
  entity_type: string;
  actor_name: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AuditEntry extends TimelineEvent {
  actor_id: string | null;
  entity_id: string;
}

export interface UserRow {
  id: string;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  pincode: string | null;
  created_at: string;
}

/** The signed-in person, with the city every record they see belongs to. */
export interface Me extends UserRow {
  city: string;
  state: string | null;
  tenant_id: string;
  city_verified: boolean;
  home_city: string;
  is_platform_admin: boolean;
}

export interface CityRow {
  id: string;
  name: string;
  slug: string;
  state: string | null;
  verified: boolean;
  is_active: boolean;
  users: number;
  incidents: number;
  created_at: string;
}

export interface CityOption {
  name: string;
  state: string | null;
}

export interface SensorReading {
  id: string;
  sensor_id: string;
  incident_id: string | null;
  latitude: number;
  longitude: number;
  reading: Record<string, number | string | boolean>;
  observed_at: string;
}

export interface Run {
  id: string;
  name: string;
  dataset_version: string;
  metrics: Record<string, number | string>;
  baseline_metrics: Record<string, number | string>;
  created_at: string;
}

export interface ModelMetrics {
  auc: number;
  average_precision: number;
  brier: number;
  precision_at_10pct: number;
}

export interface RiskModelMeta {
  version?: string;
  status: "deployed" | "kept_baseline" | "not_enough_data";
  deployed: boolean;
  reason: string;
  algorithm?: string;
  trained_at: string;
  rows_labelled: number;
  rows_total: number;
  positives: number;
  positive_rate: number | null;
  synthetic_share: number;
  train_rows?: number;
  validation_rows?: number;
  validation?: string;
  metrics?: ModelMetrics;
  baseline?: ModelMetrics & { name: string };
  candidates?: Record<string, ModelMetrics>;
  importance?: Record<string, number>;
  auc_gain_vs_baseline?: number;
  min_rows: number;
}

export interface MlStatus {
  risk: { active: "model" | "formula"; current: RiskModelMeta | null; last_run: RiskModelMeta | null };
  duplicates: { enabled: boolean; loaded: boolean; name: string | null; error: string | null };
  routing: { solver: string };
}

export interface MapPoint {
  id: string;
  latitude: number;
  longitude: number;
  status: IncidentStatus;
  severity: string | null;
  risk: number | null;
  age_hours: number;
  breached: boolean;
  description: string;
}

export interface AttentionItem {
  kind: "sla_breach" | "evidence" | "review" | "dispatch";
  reason: string;
  priority: number;
  incident: { id: string; description: string; status: IncidentStatus; latitude: number; longitude: number };
  severity: string | null;
  risk: number | null;
  age_hours: number;
}

export interface DashboardSummary {
  generated_at: string;
  sla_hours: Record<string, number>;
  counts: Partial<Record<IncidentStatus, number>>;
  kpis: {
    needs_review: { count: number; oldest_hours: number; within_target_pct: number | null };
    sla: { open: number; breached: number; at_risk: number; on_time_pct_30d: number | null; closed_30d: number };
    dispatch: { unassigned_orders: number; unrouted_orders: number; routes_awaiting_approval: number; routes_approved: number };
    in_field: { jobs: number; in_progress: number };
    evidence_to_review: number;
    verified_closure_rate_30d: number | null;
    median_hours_to_close_30d: number | null;
    verified_within_24h_pct_30d: number | null;
    repeat_sites: { count: number; share_of_reports: number | null; reports_90d: number };
  };
  flow: { date: string; created: number; closed: number }[];
  aging: { buckets: string[]; series: Record<string, number[]> };
  hotspots: { latitude: number; longitude: number; reports_90d: number; open: number; last_reported: string; sample: string; incident_id: string }[];
  workload: { worker_id: string; name: string; active_jobs: number; in_progress: number }[];
  attention: AttentionItem[];
}

export interface SystemStatus {
  ai_configured: boolean;
  ai_provider: string | null;
  worker: string;
  storage: string;
  queue: string;
  jobs_queued: number;
}

const BASE = "/api/v1";
const TOKEN_KEY = "civicloop.token";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

const TENANT_KEY = "civicloop.city";

/** A platform admin can work inside another city; this is the city they chose (null = their own). */
export function getTenant(): string | null {
  try {
    return localStorage.getItem(TENANT_KEY);
  } catch {
    return null;
  }
}

export function setTenant(id: string | null) {
  try {
    if (id) localStorage.setItem(TENANT_KEY, id);
    else localStorage.removeItem(TENANT_KEY);
  } catch {
    /* storage unavailable */
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TENANT_KEY);
    }
  } catch {
    /* storage unavailable: the session lives in memory only */
  }
}

function messageFrom(body: unknown, fallback: string): string {
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

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const city = token ? getTenant() : null;
  if (city) headers.set("X-Tenant-Id", city);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  try {
    return await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Cannot reach the CivicLoop server. Check that the backend is running.", 0);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await raw(path, init);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(messageFrom(body, `Request failed (${response.status})`), response.status);
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const query = (params: Record<string, string | number | undefined>) => {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  return entries.length ? "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&") : "";
};

function upload<T>(path: string, file: File, fields: Record<string, string> = {}) {
  const form = new FormData();
  form.append("file", file);
  Object.entries(fields).forEach(([k, v]) => form.append(k, v));
  return request<T>(path, { method: "POST", body: form });
}

export const api = {
  // identity
  login: (email: string, password: string) => post<{ access_token: string }>("/auth/login", { email, password }),
  register: (input: { name: string; email: string; password: string; city: string; state?: string; pincode: string; role?: Role }) =>
    post<{ user_id: string; email: string; role: Role; city: string; pincode: string }>("/auth/register", input),
  cities: (q: string) => request<CityOption[]>(`/tenants${query({ q })}`),
  platformCities: () => request<CityRow[]>("/platform/cities"),
  patchCity: (id: string, body: { name?: string; state?: string; verified?: boolean; is_active?: boolean }) =>
    patch<CityRow>(`/platform/cities/${id}`, body),
  mergeCity: (id: string, intoId: string) => post<CityRow>(`/platform/cities/${id}/merge`, { into_id: intoId }),
  me: () => request<Me>("/auth/me"),
  listUsers: (role?: Role) => request<UserRow[]>(`/users${query({ role })}`),
  patchUser: (id: string, body: { role?: Role; is_active?: boolean }) => patch<UserRow>(`/users/${id}`, body),

  // incidents
  listIncidents: (status?: IncidentStatus, limit = 200) =>
    request<Incident[]>(`/incidents${query({ status_filter: status, limit })}`),
  getIncident: (id: string) => request<Incident>(`/incidents/${id}`),
  createIncident: (input: {
    reporter_type: ReporterType;
    description: string;
    latitude: number;
    longitude: number;
    occurred_at: string;
    pincode?: string;
  }) => post<Incident>("/incidents", input),
  changeStatus: (id: string, status: IncidentStatus) => patch<Incident>(`/incidents/${id}/status`, { status }),
  listMedia: (id: string) => request<MediaAsset[]>(`/incidents/${id}/media`),
  uploadMedia: (id: string, file: File) => upload<MediaAsset>(`/incidents/${id}/media`, file),
  mediaBlob: async (assetId: string): Promise<Blob> => {
    const response = await raw(`/media/${assetId}/content`);
    if (!response.ok) throw new ApiError("Photo unavailable", response.status);
    return response.blob();
  },

  // AI + risk
  analyze: (id: string) => post<AnalyzeDone>(`/incidents/${id}/analysis`),
  analyzeAsync: (id: string) => post<AnalyzeQueued>(`/incidents/${id}/analysis?async_mode=true`),
  getAnalysis: (id: string) => request<Analysis | null>(`/incidents/${id}/analysis`),
  getRisk: (id: string) => request<Risk | null>(`/incidents/${id}/risk`),
  calculateRisk: (id: string) => post<Risk>(`/incidents/${id}/risk`),
  queue: (status: IncidentStatus = "ready_for_review") => request<QueueItem[]>(`/queue${query({ status })}`),
  timeline: (id: string) => request<TimelineEvent[]>(`/incidents/${id}/timeline`),

  // duplicates
  duplicates: (id: string) =>
    request<{ candidates: DuplicateCandidate[]; clusters: DuplicateCluster[]; text_method: string | null }>(
      `/incidents/${id}/duplicates`,
    ),
  createCluster: (id: string, candidate_ids: string[]) =>
    post<DuplicateCluster>(`/incidents/${id}/duplicates/cluster`, { candidate_ids }),
  confirmCluster: (id: string) => post<DuplicateCluster>(`/duplicate-clusters/${id}/confirm`),
  rejectCluster: (id: string) => post<DuplicateCluster>(`/duplicate-clusters/${id}/reject`),

  // work orders
  createOrder: (incidentId: string, body: { priority: number; estimated_volume: number | null }) =>
    post<WorkOrder>(`/incidents/${incidentId}/work-orders`, body),
  incidentOrders: (incidentId: string) => request<WorkOrder[]>(`/incidents/${incidentId}/work-orders`),
  listOrders: (status?: WorkOrderStatus) => request<WorkOrder[]>(`/work-orders${query({ status })}`),
  getOrder: (id: string) => request<WorkOrder>(`/work-orders/${id}`),
  approveOrder: (id: string) => post<WorkOrder>(`/work-orders/${id}/approve`),
  assignOrder: (id: string, worker_id: string) => post<WorkOrder>(`/work-orders/${id}/assign`, { worker_id }),
  startOrder: (id: string) => post<WorkOrder>(`/work-orders/${id}/start`),
  completeOrder: (id: string) => post<WorkOrder>(`/work-orders/${id}/complete`),
  overridePriority: (incidentId: string, priority: number, reason: string) =>
    post<WorkOrder>(`/incidents/${incidentId}/override`, { priority, reason }),

  // routes
  listRoutes: () => request<RoutePlan[]>("/routes"),
  getRoute: (id: string) => request<RoutePlan>(`/routes/${id}`),
  createRoute: (body: {
    work_order_ids: string[];
    vehicle_capacity: number;
    depot_latitude?: number;
    depot_longitude?: number;
    max_duration_minutes?: number;
  }) => post<RoutePlan>("/routes", body),
  approveRoute: (id: string) => post<RoutePlan>(`/routes/${id}/approve`),

  // verification
  submitVerification: (incidentId: string, file: File, notes: string) =>
    upload<Verification>(`/incidents/${incidentId}/verification`, file, notes ? { notes } : {}),
  getVerification: (incidentId: string) => request<Verification | null>(`/incidents/${incidentId}/verification`),
  reviewVerification: (id: string, status: VerificationStatus, reason: string) =>
    post<Verification>(`/verification/${id}/review`, { status, reason }),

  // dashboard
  dashboardSummary: (days = 14) => request<DashboardSummary>(`/dashboard/summary?days=${days}`),
  dashboardMap: () => request<MapPoint[]>("/dashboard/map"),
  previewRoute: (body: {
    work_order_ids: string[];
    vehicle_capacity: number;
    depot_latitude?: number;
    depot_longitude?: number;
    max_duration_minutes?: number;
  }) => post<RoutePlan & { total_volume: number }>("/routes/preview", body),

  badges: () => request<Partial<Record<'incidents' | 'work' | 'routes', number>>>("/me/badges"),

  // models
  mlStatus: () => request<MlStatus>("/ml/status"),
  trainRisk: () => post<{ deployed: boolean; reason: string; model: RiskModelMeta }>("/ml/risk/train"),

  // insights
  listEvaluations: () => request<Run[]>("/evaluations"),
  runEvaluation: (body: { name: string; dataset_version: string }) => post<Run>("/evaluations/run", body),
  evaluationComparison: (id: string) =>
    request<Record<string, { value: number | string; baseline: number | string | null }>>(`/evaluations/${id}/comparison`),
  listPilots: () => request<Run[]>("/pilots"),
  startPilot: (body: {
    name: string;
    location: string;
    start_date: string;
    end_date: string;
    baseline_version: string;
  }) => post<Run>("/pilots", body),
  pilotMetrics: (id: string, metrics: Record<string, number | string>) => post<Run>(`/pilots/${id}/metrics`, { metrics }),
  closePilot: (id: string) => post<Run>(`/pilots/${id}/close`),

  // integrations
  incidentSensors: (incidentId: string) => request<SensorReading[]>(`/incidents/${incidentId}/sensors`),
  recentReadings: () => request<SensorReading[]>("/sensors/readings"),
  ingestReading: (body: {
    sensor_id: string;
    latitude: number;
    longitude: number;
    reading: Record<string, number | string | boolean>;
  }) => post<SensorReading>("/sensors/readings", body),
  latestReading: (sensorId: string) => request<SensorReading>(`/sensors/${encodeURIComponent(sensorId)}/latest`),
  associateReading: (readingId: string, incident_id: string) =>
    post<SensorReading>(`/sensors/readings/${readingId}/associate`, { incident_id }),
  municipalExport: (work_order_ids: string[], system_name: string) =>
    post<{ format: string; work_orders: unknown[] }>("/municipal/export", { work_order_ids, system_name }),
  municipalImport: (updates: { work_order_id: string; status: WorkOrderStatus }[], system_name: string) =>
    post<{ imported: number; received: number }>("/municipal/import", { updates, system_name }),

  // admin
  getJob: (id: string) => request<Job>(`/jobs/${id}`),
  listJobs: (status?: Job["status"]) => request<Job[]>(`/jobs${query({ status })}`),
  retryJob: (id: string) => post<Job>(`/jobs/${id}/retry`),
  cancelJob: (id: string) => post<Job>(`/jobs/${id}/cancel`),
  audit: (entity_type?: string) => request<AuditEntry[]>(`/audit${query({ entity_type, limit: 200 })}`),
  systemStatus: () => request<SystemStatus>("/system/status"),
};

export const STATUS_ORDER: IncidentStatus[] = [
  "pending_analysis",
  "ready_for_review",
  "approved",
  "in_progress",
  "resolved",
  "verified",
  "uncertain",
  "rejected",
];

export const STATUS_LABEL: Record<IncidentStatus, string> = {
  pending_analysis: "Pending analysis",
  ready_for_review: "Ready for review",
  approved: "Approved",
  in_progress: "In progress",
  resolved: "Resolved",
  verified: "Verified",
  uncertain: "Uncertain",
  rejected: "Rejected",
};

export const ORDER_LABEL: Record<WorkOrderStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  assigned: "Assigned",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const ROLE_LABEL: Record<Role, string> = {
  reporter: "Reporter",
  supervisor: "Supervisor",
  sanitation_worker: "Sanitation worker",
  admin: "Admin",
};

export const ROLES: Role[] = ["reporter", "sanitation_worker", "supervisor", "admin"];
