import type { IncidentStatus, VehicleState, VerificationStatus, WorkOrderStatus } from "./types";

export const STATUS_LABEL: Record<IncidentStatus, string> = {
  pending_analysis: "Being checked",
  ready_for_review: "Waiting for review",
  approved: "Approved",
  in_progress: "Crew at work",
  resolved: "Cleaned, awaiting check",
  verified: "Cleaned and checked",
  uncertain: "Needs more detail",
  rejected: "Closed",
};

/** Plain-language "what happens now" for the person who reported it. */
export const STATUS_NEXT: Record<IncidentStatus, string> = {
  pending_analysis: "We are looking at your photo and place. This usually takes a minute.",
  ready_for_review: "A supervisor will review it and decide on a cleanup.",
  approved: "A cleanup is approved. A crew will be sent.",
  in_progress: "A crew is working on it now.",
  resolved: "The crew says it is clean. A supervisor will check the evidence before closing it.",
  verified: "Done. The cleanup was checked with a photo of the clean site.",
  uncertain: "A supervisor needs more detail. They may ask you or a crew to add a photo.",
  rejected: "This report was closed without a cleanup. It may be a duplicate or not a waste site.",
};

export const ORDER_LABEL: Record<WorkOrderStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  assigned: "Assigned to you",
  in_progress: "In progress",
  completed: "Done, send evidence",
  cancelled: "Cancelled",
};

export const VERIFICATION_LABEL: Record<VerificationStatus, string> = {
  pending: "Waiting for a supervisor",
  verified: "Accepted",
  uncertain: "Needs another photo",
  rejected: "Not accepted",
};

export const VEHICLE_STATE_LABEL: Record<VehicleState, string> = {
  moving: "Moving",
  idle: "Stopped",
  stale: "Signal weak",
  offline: "Offline",
  no_signal: "No signal yet",
  disabled: "Switched off",
};

/** A tone the apps map to a colour. Shown with a label too, so colour is never the only cue. */
export type Tone = "neutral" | "info" | "warn" | "good" | "bad";

export const STATUS_TONE: Record<IncidentStatus, Tone> = {
  pending_analysis: "neutral",
  ready_for_review: "warn",
  approved: "info",
  in_progress: "info",
  resolved: "info",
  verified: "good",
  uncertain: "warn",
  rejected: "bad",
};

export const ORDER_TONE: Record<WorkOrderStatus, Tone> = {
  draft: "neutral",
  approved: "info",
  assigned: "warn",
  in_progress: "info",
  completed: "good",
  cancelled: "bad",
};
