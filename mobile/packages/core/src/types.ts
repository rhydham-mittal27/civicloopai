/** The slice of the CivicLoopAI API that the two mobile apps use. Mirrors the web app's types. */

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
export type VehicleState = "moving" | "idle" | "stale" | "offline" | "no_signal" | "disabled";

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

export interface RouteStop {
  sequence: number;
  work_order_id: string;
  planned_volume: number | null;
  priority: number | null;
  order_status: WorkOrderStatus | null;
  done: boolean;
  reassigned: boolean;
  cancelled: boolean;
  incident: Incident | null;
}

/** A route the supervisor approved for this driver. Drafts are never sent to the phone. */
export interface RoutePlan {
  id: string;
  worker_id: string | null;
  worker_name: string | null;
  vehicle_id: string | null;
  approved_at: string | null;
  estimated_distance_km: number | null;
  estimated_duration_minutes: number | null;
  stops_total: number;
  stops_done: number;
  next_stop: number | null;
  active: boolean;
  created_at: string;
  stops: RouteStop[];
}

export interface Me {
  id: string;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  pincode: string | null;
  created_at: string;
  city: string;
  state: string | null;
  tenant_id: string;
}

export interface CityOption {
  name: string;
  state: string | null;
}

export interface Vehicle {
  id: string;
  label: string;
  registration: string | null;
  driver_id: string | null;
  driver_name: string | null;
  is_active: boolean;
  state: VehicleState;
  lat: number | null;
  lon: number | null;
  speed_kmh: number | null;
  heading: number | null;
  accuracy_m: number | null;
  last_seen_at: string | null;
  age_seconds: number | null;
  source: "phone" | "device" | null;
  distance_today_km: number;
}

/** A photo or file picked on the phone. React Native uploads it straight from its local uri. */
export interface UploadFile {
  uri: string;
  name: string;
  type: string;
}

export interface Fix {
  lat: number;
  lon: number;
  speed_kmh?: number;
  heading?: number;
  accuracy_m?: number;
  recorded_at?: string;
}
