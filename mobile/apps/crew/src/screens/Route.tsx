import { router, useFocusEffect } from "expo-router";
import { useCallback } from "react";
import { Linking, Text, View } from "react-native";
import { ORDER_LABEL, ORDER_TONE, mapsRouteUrl, MAPS_LEG } from "@civicloop/core";
import { Badge, Banner, Body, Button, Card, Empty, Loading, Muted, Row, Screen, TopBar, colors, font, fonts, radius, space, useLoad, useSession } from "@civicloop/ui";

/** The route the supervisor approved: stops in the planned order, the next one first, each with a Navigate button. */
export function RouteScreen({ routeId }: { routeId: string }) {
  const { api } = useSession();
  const route = useLoad(() => api.getRoute(routeId), [routeId]);

  useFocusEffect(
    useCallback(() => {
      void route.refresh();
    }, []), // eslint-disable-line react-hooks/exhaustive-deps
  );

  if (route.loading && !route.data) {
    return (
      <Screen>
        <TopBar title="Your route" onBack={() => router.back()} />
        <Loading label="Opening your route" />
      </Screen>
    );
  }
  if (!route.data) {
    return (
      <Screen>
        <TopBar title="Your route" onBack={() => router.back()} />
        <Empty title="Could not open this route" text={route.error ?? "It may have been replaced by your supervisor."} action={<Button label="Try again" onPress={route.reload} />} />
      </Screen>
    );
  }

  const plan = route.data;
  const stops = plan.stops.filter((s) => !s.reassigned && !s.cancelled);
  const progress = plan.stops_total ? plan.stops_done / plan.stops_total : 0;
  const todo = stops.filter((s) => !s.done && s.incident);
  const mapsUrl = mapsRouteUrl(todo.map((s) => s.incident!));

  return (
    <Screen onRefresh={route.refresh} refreshing={route.refreshing}>
      <TopBar title="Your route" onBack={() => router.back()} />
      <Card>
        <Row style={{ justifyContent: "space-between" }}>
          <Badge label={plan.active ? "In progress" : "Finished"} tone={plan.active ? "info" : "good"} />
          <Muted>{`${plan.stops_done} of ${plan.stops_total} done`}</Muted>
        </Row>
        <View style={{ height: 10, borderRadius: radius.pill, backgroundColor: colors.sunken, overflow: "hidden" }} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: plan.stops_total, now: plan.stops_done }}>
          <View style={{ width: `${Math.round(progress * 100)}%`, height: "100%", borderRadius: radius.pill, backgroundColor: colors.accent }} />
        </View>
        <Muted>{[plan.estimated_distance_km !== null ? `${plan.estimated_distance_km.toFixed(1)} km` : null, plan.estimated_duration_minutes !== null ? `about ${Math.round(plan.estimated_duration_minutes)} min of driving` : null].filter(Boolean).join(" · ")}</Muted>
      </Card>
      {mapsUrl ? (
        <>
          <Button label="Open the whole route in Google Maps" onPress={() => void Linking.openURL(mapsUrl)} />
          <Muted>
            {todo.length > MAPS_LEG
              ? `Google Maps takes ${MAPS_LEG} stops at a time. Open it again after these to continue with the rest.`
              : "Turn-by-turn directions through every stop left, starting from where you are now."}
          </Muted>
        </>
      ) : null}
      {!plan.active && plan.stops_total > 0 ? <Banner tone="good">Every stop on this route is done. Nice work.</Banner> : null}

      {stops.map((stop) => {
        const next = stop.sequence === plan.next_stop;
        const place = stop.incident;
        return (
          <Card key={stop.sequence} onPress={() => router.push({ pathname: "/job/[id]", params: { id: stop.work_order_id } })} label={`Stop ${stop.sequence + 1}. ${place?.description ?? "Cleanup"}`} style={stop.done ? { opacity: 0.6 } : undefined}>
            <Row style={{ gap: space.md, alignItems: "center" }}>
              <View style={{ width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center", backgroundColor: next ? colors.accent : colors.sunken }}>
                <Text style={{ fontFamily: fonts.bold, fontSize: 15, color: next ? "#ffffff" : colors.ink }}>{stop.sequence + 1}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ ...font.strong, color: colors.ink }} numberOfLines={2}>
                  {place?.description ?? "Cleanup job"}
                </Text>
                <Muted>{[stop.planned_volume !== null ? `about ${stop.planned_volume} m³` : null, stop.order_status ? ORDER_LABEL[stop.order_status] : null].filter(Boolean).join(" · ")}</Muted>
              </View>
              {stop.order_status ? <Badge label={next ? "Next" : stop.done ? "Done" : ORDER_LABEL[stop.order_status]} tone={stop.done ? "good" : next ? "info" : ORDER_TONE[stop.order_status]} /> : null}
            </Row>
            {place && !stop.done ? (
              <Button
                label="Navigate"
                variant={next ? "primary" : "secondary"}
                onPress={() => void Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
              />
            ) : null}
          </Card>
        );
      })}
      <Body>Tap a stop to open the job, start it, and send proof when it is done.</Body>
    </Screen>
  );
}
