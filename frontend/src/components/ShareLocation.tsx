"use client";

import { useEffect, useRef, useState } from "react";
import { Icon, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

const SEND_EVERY_MS = 5000;

type Note = { tone: "info" | "ok" | "warn"; text: string };

/** A crew member shares their phone's GPS as their vehicle's position. Works only while this page stays open. */
export function ShareLocation() {
  const vehicles = useLoad(() => api.myVehicles(), []);
  const [chosen, setChosen] = useState("");
  const [sharing, setSharing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [note, setNote] = useState<Note>({ tone: "info", text: "Not sharing." });
  const watch = useRef<number | null>(null);
  const lastSent = useRef(0);
  const wake = useRef<WakeLockSentinel | null>(null);

  const list = vehicles.data ?? [];
  const vehicleId = chosen || list[0]?.id || "";
  const vehicle = list.find((v) => v.id === vehicleId) ?? null;

  const release = () => {
    if (watch.current !== null) navigator.geolocation.clearWatch(watch.current);
    watch.current = null;
    wake.current?.release().catch(() => {});
    wake.current = null;
  };

  // stop quietly when the person leaves the page
  useEffect(() => release, []);

  const start = async () => {
    if (!vehicleId) return;
    if (!("geolocation" in navigator)) {
      setNote({ tone: "warn", text: "This browser cannot share a location." });
      return;
    }
    setStarting(true);
    try {
      wake.current = (await navigator.wakeLock?.request("screen")) ?? null; // keeps the screen awake so the phone keeps reporting
    } catch {
      wake.current = null; // not available, or refused: sharing still works while the page is in front
    }
    lastSent.current = 0;
    watch.current = navigator.geolocation.watchPosition(
      (pos) => {
        const now = Date.now();
        if (now - lastSent.current < SEND_EVERY_MS) return;
        lastSent.current = now;
        const { latitude, longitude, speed, heading, accuracy } = pos.coords;
        api
          .sharePosition(vehicleId, {
            lat: latitude,
            lon: longitude,
            speed_kmh: speed !== null && Number.isFinite(speed) ? Math.max(0, speed * 3.6) : undefined,
            heading: heading !== null && Number.isFinite(heading) ? heading : undefined,
            accuracy_m: Number.isFinite(accuracy) ? accuracy : undefined,
          })
          .then((r) =>
            setNote(
              r.accepted
                ? { tone: "ok", text: `Sent at ${new Date().toLocaleTimeString()} · accurate to about ${Math.round(accuracy)} m` }
                : { tone: "warn", text: "That reading looked wrong and was skipped. Waiting for a better one." },
            ),
          )
          .catch((err) => setNote({ tone: "warn", text: `${err instanceof Error ? err.message : "Could not send"}. Will try again.` }));
      },
      (err) => {
        setNote({
          tone: "warn",
          text:
            err.code === err.PERMISSION_DENIED
              ? "Location is blocked. Allow it for this site in the browser settings, then try again."
              : err.code === err.POSITION_UNAVAILABLE
                ? "No GPS signal right now. Keep the phone where it can see the sky."
                : "Finding your location is taking long. Still trying.",
        });
        if (err.code === err.PERMISSION_DENIED) {
          release();
          setSharing(false);
        }
      },
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 },
    );
    setSharing(true);
    setStarting(false);
    setNote({ tone: "info", text: "Finding your location…" });
  };

  const stop = () => {
    release();
    setSharing(false);
    setNote({ tone: "info", text: "Stopped. Your vehicle will show as offline in a few minutes." });
  };

  if (vehicles.loading && !vehicles.data) return null;
  if (list.length === 0) {
    return (
      <section className="share" aria-label="Share location">
        <div className="share-head">
          <Icon name="truck" />
          <div>
            <h2>Vehicle location</h2>
            <p className="muted">No vehicle is assigned to you. Ask a supervisor to assign one, and you can share your location from here.</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="share" aria-label="Share location" data-sharing={sharing ? "" : undefined}>
      <div className="share-head">
        <Icon name="truck" />
        <div>
          <h2>{sharing ? `Sharing ${vehicle?.label ?? "your vehicle"}'s location` : "Share my vehicle's location"}</h2>
          <p className="muted">Your supervisor sees where the vehicle is while you share. Keep this page open; phones stop sharing when the screen is off.</p>
        </div>
      </div>
      <div className="share-body">
        {list.length > 1 && (
          <div className="field">
            <label htmlFor="share-vehicle">Vehicle</label>
            <select id="share-vehicle" className="select select-sm" value={vehicleId} disabled={sharing} onChange={(e) => setChosen(e.target.value)}>
              {list.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
          </div>
        )}
        {sharing ? (
          <button className="btn" onClick={stop}>
            Stop sharing
          </button>
        ) : (
          <button className="btn btn-primary" onClick={start} disabled={starting}>
            {starting && <Spinner />}
            Start sharing
          </button>
        )}
        <p className="share-note" data-tone={note.tone} role="status">
          {sharing && <span className="live-dot" aria-hidden="true" />}
          {note.text}
        </p>
      </div>
    </section>
  );
}
