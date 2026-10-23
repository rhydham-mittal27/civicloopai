import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Linking, Text } from "react-native";
import { ORDER_LABEL, ORDER_TONE, mapsRouteUrl, whenLabel, type WorkOrder } from "@civicloop/core";
import { TabHeader } from "@civicloop/features";
import { Badge, Banner, Button, Card, Chip, Empty, Loading, Muted, Row, Screen, colors, font, space, useLoad, useSession } from "@civicloop/ui";

const TODO = new Set(["assigned", "in_progress", "approved"]);

export function JobsScreen() {
  const { api } = useSession();
  const [view, setView] = useState<"todo" | "done">("todo");
  const { data, error, loading, refreshing, refresh } = useLoad(async () => ({ orders: await api.listOrders(), routes: await api.myRoutes().catch(() => []) }), []);

  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, []), // eslint-disable-line react-hooks/exhaustive-deps
  );

  const orders = data?.orders ?? [];
  const route = (data?.routes ?? []).find((r) => r.active) ?? null;
  // the supervisor planned an order of stops, so jobs on the route follow it; the rest come after by urgency
  const mapsUrl = route
    ? mapsRouteUrl(
        route.stops
          .filter((s) => !s.done && !s.reassigned && !s.cancelled && s.incident)
          .map((s) => s.incident!),
      )
    : null;
  const place = new Map((route?.stops ?? []).map((s) => [s.work_order_id, s.sequence]));
  const todo = orders
    .filter((o) => TODO.has(o.status))
    .sort((a, b) => (place.get(a.id) ?? 1e6) - (place.get(b.id) ?? 1e6) || b.priority - a.priority);
  const done = orders.filter((o) => o.status === "completed");
  const shown: WorkOrder[] = view === "todo" ? todo : done;

  return (
    <Screen tabs onRefresh={refresh} refreshing={refreshing} header={<TabHeader title="My jobs" />}>
      {route ? (
        <Card onPress={() => router.push({ pathname: "/route/[id]", params: { id: route.id } })} label={`Your route. ${route.stops_done} of ${route.stops_total} stops done`}>
          <Row style={{ justifyContent: "space-between" }}>
            <Badge label="Your route" tone="info" />
            <Muted>{`${route.stops_done} of ${route.stops_total} done`}</Muted>
          </Row>
          <Text style={{ ...font.strong, color: colors.ink }}>
            {route.next_stop !== null ? `Next: ${route.stops.find((s) => s.sequence === route.next_stop)?.incident?.description ?? "your next stop"}` : "All stops done"}
          </Text>
          <Muted>{[route.estimated_distance_km !== null ? `${route.estimated_distance_km.toFixed(1)} km` : null, route.estimated_duration_minutes !== null ? `about ${Math.round(route.estimated_duration_minutes)} min` : null, "Your supervisor planned this order."].filter(Boolean).join(" · ")}</Muted>
          {mapsUrl ? <Button label="Open route in Google Maps" onPress={() => void Linking.openURL(mapsUrl)} /> : null}
        </Card>
      ) : null}
      <Row style={{ gap: space.sm }}>
        <Chip label={`To do (${todo.length})`} selected={view === "todo"} onPress={() => setView("todo")} />
        <Chip label={`Done (${done.length})`} selected={view === "done"} onPress={() => setView("done")} />
      </Row>
      {error && !data ? <Banner tone="bad">{error}</Banner> : null}
      {loading && !data ? <Loading label="Loading your jobs" /> : null}
      {data && shown.length === 0 ? (
        <Empty title={view === "todo" ? "Nothing to do right now" : "No finished jobs yet"} text={view === "todo" ? "New cleanups assigned to you appear here, most urgent first." : "Jobs you mark as done appear here until a supervisor checks them."} />
      ) : null}
      {shown.map((o) => (
        <Card key={o.id} onPress={() => router.push({ pathname: "/job/[id]", params: { id: o.id } })} label={`${o.incident?.description ?? "Cleanup"}. ${ORDER_LABEL[o.status]}`}>
          <Row style={{ justifyContent: "space-between" }}>
            <Badge label={ORDER_LABEL[o.status]} tone={ORDER_TONE[o.status]} />
            <Muted>{`Priority ${o.priority}`}</Muted>
          </Row>
          <Text style={{ ...font.strong, color: colors.ink }} numberOfLines={2}>
            {o.incident?.description ?? "Cleanup job"}
          </Text>
          <Muted>
            {[o.incident?.pincode ? `Pincode ${o.incident.pincode}` : null, o.estimated_volume !== null ? `about ${o.estimated_volume} m³` : null, whenLabel(o.created_at)].filter(Boolean).join(" · ")}
          </Muted>
        </Card>
      ))}
    </Screen>
  );
}
