"use client";

import { useEffect, useState } from "react";
import { api, ORDER_LABEL, STATUS_LABEL, type IncidentStatus, type WorkOrderStatus } from "@/lib/api";

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <span className="badge" data-status={status}>
      {STATUS_LABEL[status]}
    </span>
  );
}

const ORDER_TONE: Record<WorkOrderStatus, IncidentStatus> = {
  draft: "pending_analysis",
  approved: "approved",
  assigned: "ready_for_review",
  in_progress: "in_progress",
  completed: "resolved",
  cancelled: "rejected",
};

export function OrderBadge({ status }: { status: WorkOrderStatus }) {
  return (
    <span className="badge" data-status={ORDER_TONE[status]}>
      {ORDER_LABEL[status]}
    </span>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function ErrorNote({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <div className="alert" role="alert">
      {message}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function PageHead({ title, children, actions }: { title: string; children?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div aria-busy="true" className="muted" style={{ padding: "24px 0" }}>
      {label}…
    </div>
  );
}

export function RiskBar({ score, probability = false }: { score: number; probability?: boolean }) {
  const level = score >= 0.66 ? "high" : score >= 0.33 ? "mid" : "low";
  const value = Math.round(score * 100);
  return (
    <span
      className="risk"
      data-level={level}
      title={probability ? `${value}% chance of another report within 500 m in 30 days` : `Risk index ${value} out of 100`}
    >
      <span className="risk-track" aria-hidden="true">
        <span style={{ "--v": score } as React.CSSProperties} />
      </span>
      <strong>
        {value}
        {probability ? "%" : ""}
      </strong>
      <span className="sr-only">{probability ? " chance of recurrence" : " out of 100"}</span>
    </span>
  );
}

/** Photos sit behind auth, so fetch them with the token and show a blob URL. */
export function AuthImage({ assetId, alt, className }: { assetId: string; alt: string; className?: string }) {
  const [state, setState] = useState<{ id: string; url?: string; failed?: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let url: string | undefined;
    api
      .mediaBlob(assetId)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        if (!cancelled) setState({ id: assetId, url });
      })
      .catch(() => !cancelled && setState({ id: assetId, failed: true }));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [assetId]);

  if (state?.id === assetId && state.url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={state.url} alt={alt} className={className} />;
  }
  return (
    <div className={`${className ?? ""} photo-fallback`} role="img" aria-label={state?.failed ? `${alt} (unavailable)` : `${alt} (loading)`}>
      {state?.failed ? "Photo unavailable" : ""}
    </div>
  );
}

export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 12a8 8 0 1 1-2.4-5.7" />
        <path d="M20 4v4h-4" />
      </svg>
    </span>
  );
}

const icons = {
  queue: <path d="M4 6h16M4 12h16M4 18h10" />,
  plus: <path d="M12 5v14M5 12h14" />,
  back: <path d="M15 6l-6 6 6 6" />,
  out: <path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9" />,
  pin: (
    <>
      <path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z" />
      <circle cx="12" cy="9.5" r="2.5" />
    </>
  ),
  image: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="M21 16l-5-5-8 8" />
    </>
  ),
  work: (
    <>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4h6v3H9zM9 12h6M9 16h4" />
    </>
  ),
  route: (
    <>
      <circle cx="6" cy="18" r="2" />
      <circle cx="18" cy="6" r="2" />
      <path d="M8 18h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6" />
    </>
  ),
  chart: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  plug: <path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4" />,
  users: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M17 11a3 3 0 1 0 0-6M21 20c0-2.5-1.6-4.6-4-5.5" />
    </>
  ),
  jobs: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
    </>
  ),
  audit: <path d="M5 4h14v16H5zM9 9h6M9 13h6M9 17h3" />,
  check: <path d="M5 13l4 4L19 7" />,
  camera: <><path d="M4 8h3l1.5-2h7L17 8h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></>,
  review: (
    <>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4h6v3H9zM9 14l2 2 4-4" />
    </>
  ),
  alarm: (
    <>
      <circle cx="12" cy="13" r="7" />
      <path d="M12 9v4l2.5 1.5M5 4L3 6M19 4l2 2" />
    </>
  ),
  truck: (
    <>
      <path d="M3 7h11v9H3zM14 10h4l3 3v3h-7" />
      <circle cx="7" cy="17.5" r="1.8" />
      <circle cx="17" cy="17.5" r="1.8" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" />
      <path d="M9 12l2 2 4-4" />
    </>
  ),
  hourglass: <path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9" />,
  repeat: <path d="M4 11V9a3 3 0 0 1 3-3h11M15 3l3 3-3 3M20 13v2a3 3 0 0 1-3 3H6M9 21l-3-3 3-3" />,
  chev: <path d="M15 6l-6 6 6 6" />,
  search: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.2-4.2" /></>,
  fit: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  dash: <path d="M4 4h7v9H4zM13 4h7v5h-7zM13 11h7v9h-7zM4 15h7v5H4z" />,
  replay: <path d="M4 12a8 8 0 1 0 2.5-5.8M4 4v5h5" />,
} as const;

export function Icon({ name }: { name: keyof typeof icons }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {icons[name]}
    </svg>
  );
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export const pct = (value: number | null | undefined) => (value === null || value === undefined ? "–" : `${Math.round(value * 100)}%`);
