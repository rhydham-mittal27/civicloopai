import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";
import * as Location from "expo-location";
import { useEffect, useRef, useState } from "react";
import { agoFromSeconds } from "@civicloop/core";
import { TabHeader } from "@civicloop/features";
import { Badge, Banner, Body, Button, Card, Chip, Empty, Heading, Loading, Muted, Row, Screen, space, useAction, useDialog, useLoad, useSession } from "@civicloop/ui";
import { currentlySharing, deliver, readState, startSharing, stopSharing, type Mode, type ShareState } from "@/location/sharing";

const KEEP_AWAKE_TAG = "civicloop-share";

export function ShareLocationScreen() {
  const { api } = useSession();
  const dialog = useDialog();
  const vehicles = useLoad(() => api.myVehicles(), []);
  const [chosen, setChosen] = useState("");
  const [active, setActive] = useState<{ vehicleId: string; mode: Mode } | null>(null);
  const [state, setState] = useState<ShareState | null>(null);
  const watch = useRef<Location.LocationSubscription | null>(null);
  const { busy, error, run } = useAction();

  const list = vehicles.data ?? [];
  const vehicleId = chosen || active?.vehicleId || list[0]?.id || "";
  const vehicle = list.find((v) => v.id === vehicleId) ?? null;

  const stopWatch = () => {
    watch.current?.remove();
    watch.current = null;
    deactivateKeepAwake(KEEP_AWAKE_TAG).catch(() => {});
  };

  // On open: find out whether a background share is already running. A screen-open share cannot survive a restart.
  useEffect(() => {
    let live = true;
    (async () => {
      const found = await currentlySharing();
      if (!live || !found) return;
      if (found.mode === "foreground") await stopSharing();
      else setActive(found);
    })();
    return () => {
      live = false;
    };
  }, []);

  // show how the sending is going
  useEffect(() => {
    if (!active) {
      setState(null);
      return;
    }
    const read = () => void readState().then(setState);
    read();
    const timer = setInterval(read, 2000);
    return () => clearInterval(timer);
  }, [active]);

  // a screen-open share ends when the person leaves the app
  useEffect(
    () => () => {
      stopWatch();
    },
    [],
  );

  const start = () =>
    run("start", async () => {
      const permission = await Location.getForegroundPermissionsAsync();
      if (!permission.granted) {
        if (!permission.canAskAgain) {
          await dialog.openSettingsFor({ title: "Location is turned off", message: "To share your vehicle's location, allow location for CivicLoop Crew in your phone's settings.", icon: "location" });
          return;
        }
        const go = await dialog.explain({
          title: "Share your vehicle's location?",
          message: "Your supervisor will see where the vehicle is while you share. Your phone will ask you to confirm next, and may offer to allow it all the time so sharing carries on with the screen off.",
          icon: "navigate-circle",
          continueLabel: "Start sharing",
        });
        if (!go) return;
      }
      const mode = await startSharing(vehicleId);
      if (mode === "foreground") {
        stopWatch();
        watch.current = await Location.watchPositionAsync({ accuracy: Location.Accuracy.High, timeInterval: 5000, distanceInterval: 5 }, (location) => void deliver([location], api));
        await activateKeepAwakeAsync(KEEP_AWAKE_TAG).catch(() => {});
      }
      setActive({ vehicleId, mode });
    });

  const stop = () =>
    run("stop", async () => {
      stopWatch();
      await stopSharing();
      setActive(null);
    });

  if (vehicles.loading && !vehicles.data) {
    return (
      <Screen tabs>
        <Loading label="Finding your vehicle" />
      </Screen>
    );
  }

  const sinceSent = state?.at ? Math.round((Date.now() - state.at) / 1000) : null;

  return (
    <Screen tabs onRefresh={vehicles.refresh} refreshing={vehicles.refreshing} header={<TabHeader title="Vehicle location" />}>
      <Muted>Your supervisor sees where the vehicle is while you share.</Muted>

      {vehicles.error && !vehicles.data ? <Banner tone="bad">{vehicles.error}</Banner> : null}
      {vehicles.data && list.length === 0 ? <Empty title="No vehicle assigned" text="Ask your supervisor to assign a vehicle to you. Then you can share its location from here." /> : null}

      {list.length > 0 ? (
        <Card>
          <Heading>{vehicle?.label ?? "Your vehicle"}</Heading>
          {vehicle?.registration ? <Muted>{vehicle.registration}</Muted> : null}
          {list.length > 1 ? (
            <Row style={{ flexWrap: "wrap", gap: space.sm }}>
              {list.map((v) => (
                <Chip key={v.id} label={v.label} selected={v.id === vehicleId} onPress={() => !active && setChosen(v.id)} />
              ))}
            </Row>
          ) : null}

          {active ? (
            <>
              <Badge label={active.mode === "background" ? "Sharing, even with the screen off" : "Sharing while this screen is open"} tone="good" />
              <Body>
                {state?.at ? `Last sent ${agoFromSeconds(sinceSent)}${state.accuracy ? `, accurate to about ${Math.round(state.accuracy)} m` : ""}.` : "Finding your location…"}
              </Body>
              {state && state.queued > 0 ? <Banner tone="warn">{`${state.queued} reading${state.queued > 1 ? "s" : ""} waiting for a connection. They are sent when the signal returns.`}</Banner> : null}
              {state?.error ? <Banner tone="warn">{state.error}</Banner> : null}
              {active.mode === "foreground" ? <Muted>Keep this screen open and the phone awake. A full build of this app keeps sharing in the background.</Muted> : null}
              <Button label="Stop sharing" variant="secondary" busy={busy === "stop"} onPress={stop} />
            </>
          ) : (
            <>
              <Muted>
                When you start, the phone may ask to always allow location. Choosing that keeps sharing going if you switch apps or the screen turns off.
              </Muted>
              <Button label="Start sharing" busy={busy === "start"} disabled={!vehicleId} onPress={start} />
            </>
          )}
          {error ? <Banner tone="bad">{error}</Banner> : null}
        </Card>
      ) : null}
    </Screen>
  );
}
