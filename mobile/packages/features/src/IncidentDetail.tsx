import { router } from "expo-router";
import { useState, type ReactNode } from "react";
import { Linking, View } from "react-native";
import { STATUS_LABEL, STATUS_NEXT, STATUS_TONE, whenLabel } from "@civicloop/core";
import { Badge, Body, Banner, Button, Card, Empty, Gap, Heading, Loading, Muted, Row, Screen, ServerImage, TopBar, space, useAction, useDialog, useLoad, useSession } from "@civicloop/ui";
import { LocationPicker } from "./LocationPicker";
import { choosePhotos, takePhoto } from "./photos";
import { ScrollView } from "react-native";

interface Props {
  id: string;
  /** The title in the top bar. */
  title?: string;
  notice?: string;
  /** Show the buttons to add another photo to this report. */
  canAddPhoto?: boolean;
  /** Extra sections the crew app puts under the report, such as job actions. */
  children?: ReactNode;
  onChanged?: () => void;
}

/** One report: where it stands, what was found, its photos and place. Used by residents and by crews. */
export function IncidentDetail({ id, title = "Report", notice, canAddPhoto, children, onChanged }: Props) {
  const bar = <TopBar title={title} onBack={() => router.back()} />;
  const { api } = useSession();
  const dialog = useDialog();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(async () => {
    const [incident, media, analysis] = await Promise.all([api.getIncident(id), api.listMedia(id), api.getAnalysis(id).catch(() => null)]);
    return { incident, media, analysis };
  }, [id]);
  const { busy, error: actionError, run } = useAction();
  const [pickerNote, setPickerNote] = useState<string | null>(null);

  const add = async (pick: () => Promise<{ uri: string; name: string; type: string }[]>) => {
    setPickerNote(null);
    try {
      const picked = await pick();
      if (picked.length === 0) return;
      const done = await run("photo", async () => {
        for (const file of picked) await api.uploadMedia(id, file);
        return true;
      });
      if (done) {
        await reload();
        onChanged?.();
      }
    } catch (e) {
      setPickerNote(e instanceof Error ? e.message : "Could not add the photo.");
    }
  };

  if (loading && !data) {
    return (
      <Screen>
        {bar}
        <Loading label="Opening the report" />
      </Screen>
    );
  }
  if (!data) {
    return (
      <Screen onRefresh={refresh} refreshing={refreshing}>
        {bar}
        <Empty title="Could not open this report" text={error ?? "It may have been removed."} action={<Button label="Try again" onPress={reload} />} />
      </Screen>
    );
  }

  const { incident, media, analysis } = data;
  const before = media.filter((m) => !m.is_after_cleanup);
  const after = media.filter((m) => m.is_after_cleanup);

  return (
    <Screen onRefresh={refresh} refreshing={refreshing}>
      {bar}
      {notice ? <Banner tone="warn">{notice}</Banner> : null}
      <Card>
        <Row style={{ justifyContent: "space-between" }}>
          <Badge label={STATUS_LABEL[incident.status]} tone={STATUS_TONE[incident.status]} />
          <Muted>{whenLabel(incident.occurred_at)}</Muted>
        </Row>
        <Heading>{incident.description}</Heading>
        <Body>{STATUS_NEXT[incident.status]}</Body>
        {incident.pincode ? <Muted>Pincode {incident.pincode}</Muted> : null}
      </Card>

      {analysis ? (
        <Card>
          <Heading>What the software saw</Heading>
          <Body>
            {analysis.category.replace(/_/g, " ")}
            {analysis.severity ? `, ${analysis.severity} severity` : ""}
          </Body>
          <Muted>A suggestion from software. A supervisor checks it before any cleanup.</Muted>
        </Card>
      ) : null}

      <Card>
        <Heading>Photos</Heading>
        {before.length === 0 && after.length === 0 ? <Muted>No photos yet.</Muted> : null}
        {before.length > 0 ? (
          <>
            <Muted>Before cleanup</Muted>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
              {before.map((m, i) => <ServerImage key={m.id} api={api} assetId={m.id} label={`Photo ${i + 1} before cleanup`} />)}
            </ScrollView>
          </>
        ) : null}
        {after.length > 0 ? (
          <>
            <Muted>After cleanup</Muted>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
              {after.map((m, i) => <ServerImage key={m.id} api={api} assetId={m.id} label={`Photo ${i + 1} after cleanup`} />)}
            </ScrollView>
          </>
        ) : null}
        {canAddPhoto ? (
          <>
            {pickerNote ? <Banner tone="warn">{pickerNote}</Banner> : null}
            {actionError ? <Banner tone="bad">{actionError}</Banner> : null}
            <Row style={{ flexWrap: "wrap" }}>
              <Button
                label="Add a photo"
                variant="secondary"
                busy={busy === "photo"}
                onPress={() =>
                  add(async () => {
                    const shot = await takePhoto(dialog);
                    return shot ? [shot] : [];
                  })
                }
              />
              <Button label="From gallery" variant="secondary" disabled={busy === "photo"} onPress={() => add(() => choosePhotos(4))} />
            </Row>
          </>
        ) : null}
      </Card>

      <Card>
        <Heading>Where</Heading>
        <LocationPicker value={{ lat: incident.latitude, lon: incident.longitude }} interactive={false} height={180} />
        <Button label="Open in maps" variant="ghost" onPress={() => void Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${incident.latitude},${incident.longitude}`)} />
      </Card>

      {children}
      <Gap />
    </Screen>
  );
}
