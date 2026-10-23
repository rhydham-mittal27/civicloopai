import type { Role } from "./api";

export const SUPERVISORS: Role[] = ["supervisor", "admin"];
export const STAFF: Role[] = ["supervisor", "admin", "sanitation_worker"];
export const EVERYONE: Role[] = ["reporter", "sanitation_worker", "supervisor", "admin"];

export type BadgeKey = "incidents" | "work" | "routes";

export interface NavItem {
  href: string;
  label: string | ((role: Role) => string);
  icon: "dash" | "queue" | "work" | "route" | "truck" | "chart" | "plug" | "users" | "jobs" | "audit";
  roles: Role[];
  /** main = the daily workflow, tools = analysis and integrations, admin = administration. */
  group: "main" | "tools" | "admin";
  /** A live count shown beside the label, for work that is waiting on this person. */
  badge?: BadgeKey;
  /** Shown only to platform administrators (operators of the whole deployment). */
  platform?: boolean;
}

/** One table drives the sidebar and the page guards, so a link never leads to a locked page. */
export const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: "dash", roles: SUPERVISORS, group: "main" },
  { href: "/incidents", label: (r) => (r === "reporter" ? "My reports" : "Incidents"), icon: "queue", roles: EVERYONE, group: "main", badge: "incidents" },
  { href: "/work", label: (r) => (r === "sanitation_worker" ? "My assignments" : "Work orders"), icon: "work", roles: STAFF, group: "main", badge: "work" },
  { href: "/routes", label: "Routes", icon: "route", roles: SUPERVISORS, group: "main", badge: "routes" },
  { href: "/fleet", label: "Live fleet", icon: "truck", roles: SUPERVISORS, group: "main" },
  { href: "/insights", label: "Insights", icon: "chart", roles: SUPERVISORS, group: "tools" },
  { href: "/integrations", label: "Integrations", icon: "plug", roles: SUPERVISORS, group: "tools" },
  { href: "/admin/audit", label: "Audit log", icon: "audit", roles: SUPERVISORS, group: "admin" },
  { href: "/admin/users", label: "Users", icon: "users", roles: ["admin"], group: "admin" },
  { href: "/platform/cities", label: "Cities", icon: "users", roles: ["admin"], group: "admin", platform: true },
  { href: "/admin/jobs", label: "Background jobs", icon: "jobs", roles: ["admin"], group: "admin" },
];

export const resolveLabel = (item: NavItem, role: Role) => (typeof item.label === "function" ? item.label(role) : item.label);
