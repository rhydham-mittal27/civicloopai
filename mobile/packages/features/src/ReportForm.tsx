import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useRef, useState } from "react";
import { View } from "react-native";
import { isValidPincode, type Incident, type ReporterType, type UploadFile } from "@civicloop/core";
import { Banner, Button, Card, Chip, Field, Heading, Muted, PhotoStrip, Row, space, useAction, useDialog, useSession } from "@civicloop/ui";
import { LocationPicker, type Pin } from "./LocationPicker";
import { choosePhotos, takePhoto } from "./photos";
import { currentPlace } from "./place";

const MAX_PHOTOS = 4;
const QUICK = ["Overflowing bins", "Plastic litter", "Construction debris", "Garden waste", "Blocked drain", "Dead animal", "Burnt waste"];

interface Props {
  reporterType: ReporterType;
  /** Where a half-written description is kept if the app is closed by accident. */
  draftKey: string;
  /** Called once the report exists. `photosFailed` is how many photos did not upload, and `reason` is why the first one failed. */
  onCreated: (incident: Incident, photosFailed: number, reason?: string) => void;
}

/** A short random key that is the same for every attempt at sending one report. */
const newKey = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 8)}`;

export function ReportForm({ reporterType, draftKey, onCreated }: Props) {
  // sending twice (a slow network, a second tap) must give one report: the server returns the first one for the same key
  const sendKey = useRef<string>(newKey());
  const { api, me } = useSession();
  const dialog = useDialog();
  const [description, setDescription] = useState("");
  const [photos, setPhotos] = useState<UploadFile[]>([]);
  const [pin, setPin] = useState<Pin | null>(null);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [typedPincode, setTypedPincode] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ description?: string; place?: string; pincode?: string }>({});
  const [progress, setProgress] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const { busy, error, run } = useAction();
  const pincode = typedPincode ?? me?.pincode ?? "";

  useEffect(() => {
    AsyncStorage.getItem(draftKey)
      .then((saved) => saved && setDescription((current) => current || saved))
      .catch(() => {});
  }, [draftKey]);

  const updateDescription = (text: string) => {
    setDescription(text);
    setErrors((e) => ({ ...e, description: undefined }));
    (text.trim() ? AsyncStorage.setItem(draftKey, text) : AsyncStorage.removeItem(draftKey)).catch(() => {});
  };

  const addChip = (text: string) => updateDescription(description.trim() ? `${description.trim().replace(/[.,]$/, "")}. ${text}` : text);

  const addPhotos = async (pick: () => Promise<UploadFile[]>) => {
    setNotice(null);
    if (photos.length >= MAX_PHOTOS) return setNotice(`You can add up to ${MAX_PHOTOS} photos.`);
    try {
      const picked = await pick();
      setPhotos((current) => [...current, ...picked].slice(0, MAX_PHOTOS));
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not add the photo.");
    }
  };

  const useMyLocation = async () => {
    setNotice(null);
    setLocating(true);
    try {
      const here = await currentPlace(dialog);
      if (!here) return;
      setPin({ lat: here.lat, lon: here.lon });
      setAccuracy(here.accuracy);
      setErrors((e) => ({ ...e, place: undefined }));
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not find your location.");
    } finally {
      setLocating(false);
    }
  };

  const submit = async () => {
    const problems: typeof errors = {};
    if (!description.trim()) problems.description = "Tell us what you saw, in a few words.";
    if (!pin) problems.place = "Choose where it is: use your location, or tap the map.";
    if (pincode && !isValidPincode(pincode)) problems.pincode = "A pincode has 6 digits and does not start with 0.";
    setErrors(problems);
    if (problems.description || problems.place || problems.pincode || !pin) return;

    const made = await run("submit", async () => {
      setProgress("Sending your report…");
      const incident = await api.createIncident({
        reporter_type: reporterType,
        description: description.trim(),
        latitude: pin.lat,
        longitude: pin.lon,
        occurred_at: new Date().toISOString(),
        pincode: pincode || undefined,
      }, sendKey.current);
      let failed = 0;
      let reason: string | undefined;
      for (let i = 0; i < photos.length; i++) {
        setProgress(`Uploading photo ${i + 1} of ${photos.length}…`);
        try {
          await api.uploadMedia(incident.id, photos[i]!);
        } catch (e) {
          failed++;
          reason ??= e instanceof Error ? e.message : String(e);
        }
      }
      return { incident, failed, reason };
    });
    setProgress(null);
    if (!made) return;
    AsyncStorage.removeItem(draftKey).catch(() => {});
    sendKey.current = newKey(); // the next report is a new one
    setDescription("");
    setPhotos([]);
    setPin(null);
    setAccuracy(null);
    setTypedPincode(null);
    onCreated(made.incident, made.failed, made.reason);
  };

  return (
    <View style={{ gap: space.lg }}>
      <Card>
        <Heading>What did you see?</Heading>
        <Field
          label="Describe it"
          value={description}
          onChangeText={updateDescription}
          multiline
          maxLength={2000}
          placeholder="For example: bins overflowing behind the market"
          error={errors.description}
        />
        <Row style={{ flexWrap: "wrap", gap: space.sm }}>
          {QUICK.map((q) => (
            <Chip key={q} label={q} onPress={() => addChip(q)} />
          ))}
        </Row>
      </Card>

      <Card>
        <Heading>Add photos</Heading>
        <Muted>A clear photo helps the supervisor decide faster. Up to {MAX_PHOTOS}.</Muted>
        <PhotoStrip photos={photos} onRemove={(i) => setPhotos((p) => p.filter((_, idx) => idx !== i))} />
        <Row style={{ flexWrap: "wrap" }}>
          <Button
            label="Take a photo"
            variant="secondary"
            onPress={() =>
              addPhotos(async () => {
                const shot = await takePhoto(dialog);
                return shot ? [shot] : [];
              })
            }
          />
          <Button label="From gallery" variant="secondary" onPress={() => addPhotos(() => choosePhotos(MAX_PHOTOS - photos.length))} />
        </Row>
      </Card>

      <Card>
        <Heading>Where is it?</Heading>
        <Button label={locating ? "Finding you…" : "Use my location"} variant="secondary" busy={locating} onPress={useMyLocation} />
        <LocationPicker
          value={pin}
          onChange={(p) => {
            setPin(p);
            setAccuracy(null);
            setErrors((e) => ({ ...e, place: undefined }));
          }}
        />
        {errors.place ? <Banner tone="bad">{errors.place}</Banner> : <Muted>{pin ? `Pin placed${accuracy ? `, accurate to about ${Math.round(accuracy)} m` : ""}. Tap the map to move it.` : "Tap the map to drop a pin, or use your location."}</Muted>}
        <Field
          label="Area pincode"
          value={pincode}
          onChangeText={(t) => {
            setTypedPincode(t.replace(/\D/g, "").slice(0, 6));
            setErrors((e) => ({ ...e, pincode: undefined }));
          }}
          keyboardType="number-pad"
          maxLength={6}
          placeholder="160017"
          hint={me?.city ? `Starts as your own pincode in ${me.city}. Change it if the waste is somewhere else.` : undefined}
          error={errors.pincode}
        />
      </Card>

      {notice ? <Banner tone="warn">{notice}</Banner> : null}
      {error ? <Banner tone="bad">{error}</Banner> : null}
      <Button label={busy ? (progress ?? "Sending…") : "Submit report"} busy={!!busy} onPress={submit} />
    </View>
  );
}
