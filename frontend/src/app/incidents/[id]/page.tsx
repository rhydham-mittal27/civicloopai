"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  AnalysisSection,
  DecisionCard,
  DuplicatesSection,
  PhotosSection,
  RiskCard,
  SensorsSection,
  TimelineSection,
  VerificationSection,
  WorkOrderCard,
  WorkerCard,
} from "@/components/incident/sections";
import { Icon, Loading, StatusBadge, formatWhen, shortId } from "@/components/ui";
import { api } from "@/lib/api";
import { isStaff, isSupervisor, useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";

export default function IncidentPage() {
  return (
    <AppShell>
      <Detail />
    </AppShell>
  );
}

function Detail() {
  const { id } = useParams<{ id: string }>();
  const { principal } = useAuth();
  const staff = isStaff(principal?.role);
  const supervisor = isSupervisor(principal?.role);
  const worker = principal?.role === "sanitation_worker";

  const core = useLoad(async () => {
    const [incident, media, analysis, verification] = await Promise.all([
      api.getIncident(id),
      api.listMedia(id),
      api.getAnalysis(id),
      api.getVerification(id),
    ]);
    return { incident, media, analysis, verification };
  }, [id]);

  const staffData = useLoad(async () => {
    if (!staff) return null;
    const [risk, orders, timeline] = await Promise.all([api.getRisk(id), api.incidentOrders(id), api.timeline(id)]);
    return { risk, orders, timeline };
  }, [id, staff]);

  const refresh = () => {
    core.reload();
    staffData.reload();
  };

  if (core.error && !core.data) {
    const notFound = /not found/i.test(core.error);
    return (
      <>
        <Link href="/incidents" className="back">
          <Icon name="back" />
          Incidents
        </Link>
        <div className="empty" style={{ justifyItems: "start", textAlign: "left", padding: "24px 0" }}>
          <h1>{notFound ? "Incident not found" : "Could not load this incident"}</h1>
          <p>{notFound ? "It may have been removed, or it is not one of yours." : core.error}</p>
        </div>
      </>
    );
  }
  if (!core.data) return <Loading label="Loading incident" />;

  const { incident, media, analysis, verification } = core.data;
  const { risk, orders, timeline } = staffData.data ?? { risk: undefined, orders: [], timeline: undefined };
  const hasBefore = media.some((m) => !m.is_after_cleanup);
  const hasPanel = staff;

  return (
    <>
      <Link href="/incidents" className="back">
        <Icon name="back" />
        Incidents
      </Link>

      <div className="detail" data-single={hasPanel ? undefined : ""}>
        <div>
          <h1>{incident.description}</h1>
          <div className="detail-meta">
            <StatusBadge status={incident.status} />
            <span className="mono muted">#{shortId(incident.id)}</span>
            <span className="muted">Seen {formatWhen(incident.occurred_at)}</span>
          </div>

          <section className="section" aria-labelledby="where">
            <h2 id="where">Site</h2>
            <dl className="facts">
              <div>
                <dt>Latitude</dt>
                <dd className="mono">{incident.latitude.toFixed(6)}</dd>
              </div>
              <div>
                <dt>Longitude</dt>
                <dd className="mono">{incident.longitude.toFixed(6)}</dd>
              </div>
              {incident.pincode && (
                <div>
                  <dt>Pincode</dt>
                  <dd className="mono">{incident.pincode}</dd>
                </div>
              )}
              <div>
                <dt>Reported by</dt>
                <dd>{incident.reporter_type.replace("_", " ")}</dd>
              </div>
            </dl>
            <div>
              <a
                className="btn"
                target="_blank"
                rel="noreferrer"
                href={`https://www.google.com/maps/search/?api=1&query=${incident.latitude},${incident.longitude}`}
              >
                <Icon name="pin" />
                Show on Google Maps
              </a>
            </div>
          </section>

          <PhotosSection incidentId={id} media={media} onChange={refresh} />
          <AnalysisSection incident={incident} analysis={analysis} canRun={staff} hasPhoto={hasBefore} onDone={refresh} />
          <VerificationSection verification={verification} canReview={supervisor && !!verification && verification.status !== "rejected"} onDone={refresh} />
          {supervisor && <DuplicatesSection incidentId={id} />}
          {supervisor && <SensorsSection incidentId={id} />}
          {staff && <TimelineSection events={timeline} />}
        </div>

        {hasPanel && (
          <aside className="panel" aria-label="Actions">
            {staff && <RiskCard incidentId={id} risk={risk} canRecalc={supervisor} onDone={refresh} />}
            {supervisor && <DecisionCard incident={incident} onDone={refresh} />}
            {supervisor && <WorkOrderCard incident={incident} orders={orders} risk={risk} onDone={refresh} />}
            {worker && <WorkerCard incident={incident} orders={orders} onDone={refresh} />}
          </aside>
        )}
      </div>
    </>
  );
}
