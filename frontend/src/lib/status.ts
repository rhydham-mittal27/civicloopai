import type { IncidentStatus } from "./api";

export type Shape = "circle" | "triangle" | "square" | "diamond" | "hexagon" | "dot";

export interface StatusStyle {
  label: string;
  /** Colour-blind-safe (Okabe-Ito based). Never the only cue: each status also has its own shape. */
  color: string;
  shape: Shape;
  hollow?: boolean;
}

export const STATUS_STYLE: Record<IncidentStatus, StatusStyle> = {
  pending_analysis: { label: "Pending analysis", color: "#5b6b82", shape: "circle", hollow: true },
  ready_for_review: { label: "Ready for review", color: "#e69f00", shape: "triangle" },
  approved: { label: "Approved", color: "#0072b2", shape: "square" },
  in_progress: { label: "In progress", color: "#cc79a7", shape: "diamond" },
  uncertain: { label: "Needs a decision", color: "#d55e00", shape: "hexagon" },
  resolved: { label: "Resolved", color: "#009e73", shape: "dot" },
  verified: { label: "Verified", color: "#009e73", shape: "dot" },
  rejected: { label: "Rejected", color: "#8a94a6", shape: "dot" },
};

/** Statuses the dashboard map shows by default; the rest can be switched on from the legend. */
export const MAP_PRIMARY: IncidentStatus[] = ["pending_analysis", "ready_for_review", "approved"];
export const MAP_SECONDARY: IncidentStatus[] = ["in_progress", "uncertain"];
export const MAP_CLOSED: IncidentStatus[] = ["resolved", "verified"];

/** Points of a polygon marker of radius r, centred on the origin. */
export function shapePoints(shape: Shape, r: number): string {
  switch (shape) {
    case "triangle":
      return `0,${-r * 1.2} ${r * 1.1},${r * 0.85} ${-r * 1.1},${r * 0.85}`;
    case "square":
      return `${-r * 0.95},${-r * 0.95} ${r * 0.95},${-r * 0.95} ${r * 0.95},${r * 0.95} ${-r * 0.95},${r * 0.95}`;
    case "diamond":
      return `0,${-r * 1.3} ${r * 1.3},0 0,${r * 1.3} ${-r * 1.3},0`;
    case "hexagon":
      return [0, 1, 2, 3, 4, 5].map((i) => `${(Math.cos((Math.PI / 3) * i) * r * 1.15).toFixed(2)},${(Math.sin((Math.PI / 3) * i) * r * 1.15).toFixed(2)}`).join(" ");
    default:
      return "";
  }
}
