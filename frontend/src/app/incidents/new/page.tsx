"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { LocationPicker, type PickerHandle } from "@/components/map/LocationPicker";
import { useToast } from "@/components/Toast";
import { Icon, PageHead, Spinner } from "@/components/ui";
import { api, type ReporterType } from "@/lib/api";
import { isSupervisor, useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";
import type { LatLon } from "@/lib/map";

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_PHOTOS = 4;
const DRAFT_KEY = "civicloop.report-draft";

const QUICK = ["Overflowing bins", "Construction rubble", "Garbage burning", "Dead animal", "Blocked drain", "Bulky items dumped", "Medical waste", "Plastic litter"];

const NEXT_STEPS = [
  ["AI looks at your photo", "It suggests what kind of waste this is and how bad it looks."],
  ["A supervisor reviews it", "They approve the cleanup, or ask for more detail."],
  ["A crew cleans the site", "You can follow progress from My reports."],
  ["The cleanup is checked", "Nothing is closed until there is a photo of the clean site."],
];

function readDraft(): string {
  try {
    return localStorage.getItem(DRAFT_KEY) ?? "";
  } catch {
    return "";
  }
}

function localNow(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

export default function NewIncidentPage() {
  return (
    <AppShell>
      <ReportForm />
    </AppShell>
  );
}

function ReportForm() {
  const { principal } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const picker = useRef<PickerHandle>(null);
  // one key per report: a retry or a second click returns the first report instead of making another
  const sendKey = useRef<string>(typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now()));
  const canChooseReporter = isSupervisor(principal?.role);

  const [description, setDescription] = useState(readDraft);
  const [place, setPlace] = useState<LatLon | null>(null);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [when, setWhen] = useState<"now" | "earlier">("now");
  const [earlier, setEarlier] = useState(localNow);
  const [reporterType, setReporterType] = useState<ReporterType>(principal?.role === "sanitation_worker" ? "field_worker" : principal?.role === "reporter" ? "resident" : "supervisor");
  const me = useLoad(() => api.me(), []);
  const [pincodeEdit, setPincodeEdit] = useState<string | null>(null);
  const pincode = pincodeEdit ?? me.data?.pincode ?? "";
  const [locating, setLocating] = useState(false);
  const [locNote, setLocNote] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ description?: string; place?: string; pincode?: string; photos?: string; form?: string }>({});
  const [stage, setStage] = useState<{ step: "idle" | "report" | "photo"; n?: number }>({ step: "idle" });

  // keep a half-written description if the page is closed by accident
  useEffect(() => {
    try {
      if (description.trim()) localStorage.setItem(DRAFT_KEY, description);
      else localStorage.removeItem(DRAFT_KEY);
    } catch {
      /* drafts are a convenience only */
    }
  }, [description]);

  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);

  function setPlaceFrom(next: LatLon, gpsAccuracy: number | null = null) {
    setPlace(next);
    setAccuracy(gpsAccuracy);
    setLat(next.lat.toFixed(6));
    setLon(next.lon.toFixed(6));
    setErrors((e) => ({ ...e, place: undefined }));
  }

  function typedCoordinates(nextLat: string, nextLon: string) {
    setLat(nextLat);
    setLon(nextLon);
    const a = Number(nextLat);
    const b = Number(nextLon);
    if (nextLat !== "" && nextLon !== "" && Number.isFinite(a) && Number.isFinite(b) && Math.abs(a) <= 90 && Math.abs(b) <= 180) {
      setPlace({ lat: a, lon: b });
      setAccuracy(null);
      picker.current?.flyTo({ lat: a, lon: b });
      setErrors((e) => ({ ...e, place: undefined }));
    }
  }

  function locate() {
    setLocNote(null);
    if (!navigator.geolocation) {
      setLocNote("This browser cannot share its location. Tap the map instead.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const here = { lat: position.coords.latitude, lon: position.coords.longitude };
        setPlaceFrom(here, position.coords.accuracy);
        picker.current?.flyTo(here);
        setLocating(false);
      },
      () => {
        setLocNote("Location permission was denied. Tap the map to place the pin instead.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    const next: File[] = [...files];
    let problem: string | undefined;
    for (const file of Array.from(list)) {
      if (!file.type.startsWith("image/")) problem = "Only image files can be attached.";
      else if (file.size > MAX_BYTES) problem = `${file.name} is over 10 MB. Choose a smaller photo.`;
      else if (next.length >= MAX_PHOTOS) problem = `You can attach up to ${MAX_PHOTOS} photos.`;
      else next.push(file);
    }
    setFiles(next);
    setErrors((e) => ({ ...e, photos: problem }));
  }

  function addChip(text: string) {
    setDescription((current) => (current.trim() ? `${current.trim().replace(/[.,]$/, "")}. ${text}` : text));
    setErrors((e) => ({ ...e, description: undefined }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problems: typeof errors = {};
    if (!description.trim()) problems.description = "Tell us what you saw, in a few words.";
    if (!place) problems.place = "Choose where it is: tap the map or use your location.";
    if (pincode && !/^[1-9][0-9]{5}$/.test(pincode)) problems.pincode = "A pincode has 6 digits and does not start with 0.";
    setErrors(problems);
    if (problems.description || problems.place || problems.pincode) return;

    setStage({ step: "report" });
    let incidentId: string;
    try {
      const incident = await api.createIncident({
        reporter_type: reporterType,
        description: description.trim(),
        latitude: place!.lat,
        longitude: place!.lon,
        occurred_at: (when === "now" ? new Date() : new Date(earlier)).toISOString(),
        pincode: pincode || undefined,
      }, sendKey.current);
      incidentId = incident.id;
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : "Could not submit the report" });
      setStage({ step: "idle" });
      return;
    }

    let failed = 0;
    for (let i = 0; i < files.length; i++) {
      setStage({ step: "photo", n: i + 1 });
      try {
        await api.uploadMedia(incidentId, files[i]);
      } catch {
        failed++;
      }
    }
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch {
      /* nothing to clear */
    }
    toast(failed ? `Report saved, but ${failed} photo${failed > 1 ? "s" : ""} did not upload. Add them from the report page.` : files.length ? "Report submitted with photos" : "Report submitted");
    router.push(`/incidents/${incidentId}`);
  }

  const busy = stage.step !== "idle";
  const steps = [
    { done: description.trim().length > 0, label: "What you saw", need: true },
    { done: !!place, label: "Where it is", need: true },
    { done: files.length > 0, label: "A photo", need: false },
  ];

  return (
    <>
      <PageHead title="Report an incident">Add what you saw, where it is and a photo. It takes under a minute.</PageHead>

      <form className="report" onSubmit={submit} noValidate>
        <div className="report-main">
          {errors.form && (
            <div className="alert" role="alert">
              {errors.form}
            </div>
          )}

          <section className="rsec">
            <header>
              <span className="step-n">1</span>
              <div>
                <h2>What did you see?</h2>
                <p className="muted">A few words are enough. Tap a suggestion to start.</p>
              </div>
            </header>
            <div className="chips-row" role="group" aria-label="Quick descriptions">
              {QUICK.map((q) => (
                <button key={q} type="button" className="chip chip-quick" onClick={() => addChip(q)}>
                  {q}
                </button>
              ))}
            </div>
            <div className="field">
              <label htmlFor="description" className="sr-only">
                What did you see?
              </label>
              <textarea
                id="description"
                className="textarea"
                required
                maxLength={600}
                value={description}
                aria-invalid={errors.description ? "true" : undefined}
                aria-describedby="description-help"
                onChange={(e) => {
                  setDescription(e.target.value);
                  if (e.target.value.trim()) setErrors((x) => ({ ...x, description: undefined }));
                }}
                placeholder="Overflowing bins behind the market, construction debris on the footpath…"
              />
              <div id="description-help" className="field-foot">
                <span className={errors.description ? "field-error" : "hint"}>{errors.description ?? "Mention a landmark if you can."}</span>
                <span className="hint count-text">{description.length}/600</span>
              </div>
            </div>
          </section>

          <section className="rsec">
            <header>
              <span className="step-n">2</span>
              <div>
                <h2>Where is it?</h2>
                <p className="muted">Tap the map to drop a pin, or let your phone find you.</p>
              </div>
              <button type="button" className="btn" onClick={locate} disabled={locating}>
                {locating ? <Spinner /> : <Icon name="pin" />}
                {locating ? "Finding you" : "Use my location"}
              </button>
            </header>
            <LocationPicker ref={picker} value={place} onChange={(p) => setPlaceFrom(p)} accuracy={accuracy} />
            <div className="field-foot">
              <span className={errors.place ? "field-error" : "hint"} role={errors.place ? "alert" : undefined}>
                {errors.place ??
                  (place ? (
                    <>
                      Pin at <span className="mono">{place.lat.toFixed(5)}, {place.lon.toFixed(5)}</span>
                      {accuracy ? ` · accurate to about ${Math.round(accuracy)} m` : ""}
                    </>
                  ) : (
                    "No location chosen yet."
                  ))}
              </span>
              {locNote && <span className="hint">{locNote}</span>}
            </div>
            <div className="field form-narrow">
              <label htmlFor="area-pin">
                Area pincode{me.data?.city ? <span className="muted"> · {me.data.city}</span> : null}
              </label>
              <input
                id="area-pin"
                className="input mono"
                inputMode="numeric"
                maxLength={6}
                placeholder="160017"
                value={pincode}
                aria-invalid={errors.pincode ? true : undefined}
                onChange={(e) => {
                  setPincodeEdit(e.target.value.replace(/\D/g, ""));
                  setErrors((p) => ({ ...p, pincode: undefined }));
                }}
              />
              <span className={errors.pincode ? "field-error" : "hint"} role={errors.pincode ? "alert" : undefined}>
                {errors.pincode ?? "Where the waste is. Starts as your own pincode; change it if you are elsewhere."}
              </span>
            </div>
            <details className="depot-fields">
              <summary>Enter exact coordinates</summary>
              <div className="split">
                <div className="field">
                  <label htmlFor="lat">Latitude</label>
                  <input id="lat" className="input mono" inputMode="decimal" placeholder="30.7333" value={lat} onChange={(e) => typedCoordinates(e.target.value, lon)} />
                </div>
                <div className="field">
                  <label htmlFor="lon">Longitude</label>
                  <input id="lon" className="input mono" inputMode="decimal" placeholder="76.7794" value={lon} onChange={(e) => typedCoordinates(lat, e.target.value)} />
                </div>
              </div>
            </details>
          </section>

          <section className="rsec">
            <header>
              <span className="step-n">3</span>
              <div>
                <h2>Add photos</h2>
                <p className="muted">Show the whole site, and a close-up if it helps. Up to {MAX_PHOTOS}.</p>
              </div>
            </header>
            <div className="photos">
              {previews.map((src, i) => (
                <figure key={src} className="shot">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={src} alt={`Attached photo ${i + 1}`} />
                  <button type="button" className="shot-remove" aria-label={`Remove photo ${i + 1}`} onClick={() => setFiles((f) => f.filter((_, j) => j !== i))}>
                    ×
                  </button>
                  {i === 0 && <figcaption>Main photo</figcaption>}
                </figure>
              ))}
              {files.length < MAX_PHOTOS && (
                <div className="shot-add">
                  <label className="dropzone">
                    <Icon name="image" />
                    <strong>{files.length ? "Add another" : "Add photos"}</strong>
                    <span className="hint">JPEG or PNG, up to 10 MB</span>
                    <input id="photo-input" className="sr-only" type="file" accept="image/*" multiple onChange={(e) => (addFiles(e.target.files), (e.target.value = ""))} />
                  </label>
                  <label className="btn camera">
                    <Icon name="camera" />
                    Take a photo
                    <input className="sr-only" type="file" accept="image/*" capture="environment" onChange={(e) => (addFiles(e.target.files), (e.target.value = ""))} />
                  </label>
                </div>
              )}
            </div>
            {errors.photos && (
              <span className="field-error" role="alert">
                {errors.photos}
              </span>
            )}
          </section>

          <section className="rsec">
            <header>
              <span className="step-n">4</span>
              <div>
                <h2>When did you see it?</h2>
              </div>
            </header>
            <div className="segmented" role="radiogroup" aria-label="When">
              {(
                [
                  ["now", "Just now"],
                  ["earlier", "Earlier"],
                ] as const
              ).map(([value, label]) => (
                <label key={value}>
                  <input className="sr-only" type="radio" name="when" value={value} checked={when === value} onChange={() => setWhen(value)} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            {when === "earlier" && (
              <div className="field form-narrow">
                <label htmlFor="when">Date and time</label>
                <input id="when" className="input" type="datetime-local" max={localNow()} value={earlier} onChange={(e) => setEarlier(e.target.value)} />
              </div>
            )}
            {canChooseReporter && (
              <div className="field form-narrow">
                <label htmlFor="by">Reporting on behalf of</label>
                <select id="by" className="select" value={reporterType} onChange={(e) => setReporterType(e.target.value as ReporterType)}>
                  <option value="resident">A resident</option>
                  <option value="field_worker">A field worker</option>
                  <option value="supervisor">Myself, as a supervisor</option>
                </select>
              </div>
            )}
          </section>
        </div>

        <aside className="report-side" aria-label="Summary">
          <div className="summary">
            <h2>Your report</h2>
            <ul className="checklist">
              {steps.map((s) => (
                <li key={s.label} data-done={s.done ? "" : undefined}>
                  <span className="tick" aria-hidden="true">
                    {s.done ? <Icon name="check" /> : null}
                  </span>
                  <span>
                    {s.label}
                    {!s.need && !s.done && <em> · recommended</em>}
                  </span>
                  <span className="sr-only">{s.done ? "done" : "not yet"}</span>
                </li>
              ))}
            </ul>
            {previews[0] && (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="summary-photo" src={previews[0]} alt="" />
            )}
            <button className="btn btn-primary btn-block btn-lg" disabled={busy}>
              {busy && <Spinner />}
              {stage.step === "report" ? "Submitting report" : stage.step === "photo" ? `Uploading photo ${stage.n} of ${files.length}` : "Submit report"}
            </button>
            <p className="hint">Your report goes to the city&apos;s sanitation supervisors.</p>
          </div>

          <div className="next-steps">
            <h2>What happens next</h2>
            <ol>
              {NEXT_STEPS.map(([title, body], i) => (
                <li key={title}>
                  <span className="stop-n">{i + 1}</span>
                  <div>
                    <strong>{title}</strong>
                    <span className="muted">{body}</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </aside>
      </form>
    </>
  );
}
