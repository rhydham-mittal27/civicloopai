import { router } from "expo-router";
import { useState } from "react";
import { Linking } from "react-native";
import { ORDER_LABEL, ORDER_TONE, VERIFICATION_LABEL, type WorkOrder } from "@civicloop/core";
import { choosePhotos, IncidentDetail, takePhoto } from "@civicloop/features";
import { Badge, Banner, Body, Button, Card, Empty, Heading, Loading, Muted, Row, Screen, TopBar, space, useAction, useDialog, useLoad, useSession } from "@civicloop/ui";

/** One job: the report on top, the crew's steps under it. */
export function JobDetailScreen({ orderId }: { orderId: string }) {
  const { api } = useSession();
  const dialog = useDialog();
  const order = useLoad(() => api.getOrder(orderId), [orderId]);
  const verification = useLoad(async () => {
    const o = await api.getOrder(orderId);
    return api.getVerification(o.incident_id).catch(() => null);
  }, [orderId]);
  const { busy, error, run } = useAction();
  const [note, setNote] = useState<string | null>(null);

  if (order.loading && !order.data) {
    return (
      <Screen>
        <TopBar title="Job" onBack={() => router.back()} />
        <Loading label="Opening the job" />
      </Screen>
    );
  }
  if (!order.data) {
    return (
      <Screen>
        <TopBar title="Job" onBack={() => router.back()} />
        <Empty title="Could not open this job" text={order.error ?? "It may no longer be assigned to you."} action={<Button label="Try again" onPress={order.reload} />} />
      </Screen>
    );
  }
  const job: WorkOrder = order.data;
  const proof = verification.data;

  const move = (key: string, fn: () => Promise<unknown>) =>
    run(key, async () => {
      await fn();
      await order.reload();
    });

  const confirmDone = async () => {
    const yes = await dialog.confirm({
      title: "Mark this cleanup as done?",
      message: "You will then send a photo of the clean site. A supervisor checks it before the report is closed.",
      confirmLabel: "Yes, it is done",
      cancelLabel: "Not yet",
      tone: "good",
      icon: "checkmark-circle",
    });
    if (yes) await move("complete", () => api.completeOrder(job.id));
  };

  const sendEvidence = async (fromGallery: boolean) => {
    setNote(null);
    try {
      const file = fromGallery ? (await choosePhotos(1))[0] : await takePhoto(dialog);
      if (!file) return;
      const sent = await run("evidence", () => api.submitEvidence(job.incident_id, file));
      if (sent) {
        setNote("Photo sent. A supervisor will check it.");
        await verification.reload();
      }
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not add the photo.");
    }
  };

  const steps = [
    { label: "Assigned to you", done: true },
    { label: "Work started", done: job.status === "in_progress" || job.status === "completed" },
    { label: "Marked as done", done: job.status === "completed" },
    { label: "After-photo sent", done: !!proof },
    { label: "Checked by a supervisor", done: proof?.status === "verified" },
  ];

  return (
    <IncidentDetail id={job.incident_id} title="Job" canAddPhoto={false} onChanged={() => void order.reload()}>
      <Card>
        <Row style={{ justifyContent: "space-between" }}>
          <Heading>Your steps</Heading>
          <Badge label={ORDER_LABEL[job.status]} tone={ORDER_TONE[job.status]} />
        </Row>
        {steps.map((s) => (
          <Body key={s.label} style={{ opacity: s.done ? 1 : 0.55 }}>
            {s.done ? "✓  " : "○  "}
            {s.label}
          </Body>
        ))}
        {proof ? <Muted>{`After-photo: ${VERIFICATION_LABEL[proof.status]}${proof.review_reason ? `. ${proof.review_reason}` : ""}`}</Muted> : null}
      </Card>

      {error ? <Banner tone="bad">{error}</Banner> : null}
      {note ? <Banner tone="info">{note}</Banner> : null}

      <Card>
        <Button
          label="Navigate to the site"
          variant="secondary"
          onPress={() => void Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${job.incident?.latitude},${job.incident?.longitude}`)}
        />
        {job.status === "assigned" ? <Button label="Start work" busy={busy === "start"} onPress={() => void move("start", () => api.startOrder(job.id))} /> : null}
        {job.status === "in_progress" ? <Button label="Mark as done" busy={busy === "complete"} onPress={() => void confirmDone()} /> : null}
        {job.status === "completed" && proof?.status !== "verified" ? (
          <>
            <Muted>{proof ? "Add another photo if a supervisor asked for one." : "Take a photo of the clean site from where the waste was."}</Muted>
            <Row style={{ flexWrap: "wrap", gap: space.sm }}>
              <Button label="Take after-photo" busy={busy === "evidence"} onPress={() => void sendEvidence(false)} />
              <Button label="From gallery" variant="secondary" disabled={busy === "evidence"} onPress={() => void sendEvidence(true)} />
            </Row>
          </>
        ) : null}
        {job.status === "completed" && proof?.status === "verified" ? <Banner tone="good">A supervisor accepted your photo. This job is closed.</Banner> : null}
      </Card>
    </IncidentDetail>
  );
}
