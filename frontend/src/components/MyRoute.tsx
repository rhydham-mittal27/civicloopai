"use client";

import Link from "next/link";
import { Icon } from "@/components/ui";
import { api } from "@/lib/api";
import { MAPS_LEG, mapsRouteUrl } from "@/lib/maps";
import { useLoad } from "@/lib/hooks";

/** The route the supervisor approved for this driver: stops in order, with the next one highlighted. */
export function MyRoute() {
  const routes = useLoad(() => api.myRoutes(), []);
  const list = (routes.data ?? []).filter((r) => r.active);
  if (list.length === 0) return null;
  return (
    <>
      {list.map((route) => {
        const total = route.stops_total ?? route.stops.length;
        const done = route.stops_done ?? 0;
        return (
          <section key={route.id} className="my-route" aria-label="Your route">
            <div className="my-route-head">
              <h2>
                <Icon name="route" /> Your route
              </h2>
              <span className="badge" data-status="verified">
                {done} of {total} done
              </span>
            </div>
            <div className="fillbar thin" role="img" aria-label={`${done} of ${total} stops done`}>
              <span style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
            </div>
            {mapsRouteUrl(route) && (
              <div className="btn-row">
                <a className="btn btn-primary" href={mapsRouteUrl(route)!} target="_blank" rel="noreferrer">
                  Open the whole route in Google Maps
                </a>
                <span className="muted hint">{route.stops.filter((s) => !s.done).length > MAPS_LEG ? `Google Maps takes ${MAPS_LEG} stops at a time.` : "Live turn-by-turn through every stop left."}</span>
              </div>
            )}
            <ol className="stops">
              {route.stops
                .filter((s) => !s.reassigned && !s.cancelled)
                .map((stop) => (
                  <li key={stop.sequence} data-done={stop.done ? "" : undefined} data-next={stop.sequence === route.next_stop ? "" : undefined}>
                    <span className="stop-n">{stop.sequence + 1}</span>
                    <div>
                      {stop.incident ? <Link href={`/incidents/${stop.incident.id}`}>{stop.incident.description}</Link> : <span>Stop {stop.sequence + 1}</span>}
                      <div className="row-sub">
                        <span>{stop.done ? "Done" : stop.sequence === route.next_stop ? "Next stop" : "Later"}</span>
                        {stop.incident && (
                          <a href={`https://www.google.com/maps/dir/?api=1&destination=${stop.incident.latitude},${stop.incident.longitude}`} target="_blank" rel="noreferrer">
                            Navigate
                          </a>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
            </ol>
          </section>
        );
      })}
    </>
  );
}
