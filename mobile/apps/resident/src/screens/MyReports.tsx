import { router, useFocusEffect } from "expo-router";
import { useCallback } from "react";
import { Text } from "react-native";
import { STATUS_LABEL, STATUS_TONE, whenLabel } from "@civicloop/core";
import { TabHeader } from "@civicloop/features";
import { Badge, Banner, Button, Card, Empty, Loading, Muted, Row, Screen, colors, font, useLoad, useSession } from "@civicloop/ui";

export function MyReportsScreen() {
  const { api, me } = useSession();
  const { data, error, loading, refreshing, refresh } = useLoad(() => api.listIncidents(undefined, 100), []);

  // coming back from a new report or a detail screen shows the latest status
  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, []), // eslint-disable-line react-hooks/exhaustive-deps
  );

  const reports = data ?? [];
  return (
    <Screen tabs onRefresh={refresh} refreshing={refreshing} header={<TabHeader title="My reports" subtitle={me ? `${me.city}${me.pincode ? ` · ${me.pincode}` : ""}` : undefined} />}>
      {error && !data ? <Banner tone="bad">{error}</Banner> : null}
      {loading && !data ? <Loading label="Loading your reports" /> : null}
      {data && reports.length === 0 ? (
        <Empty
          title="No reports yet"
          text="See waste that should be cleaned? Report it with a photo and a pin. You can follow it here until it is done."
          action={<Button label="Report waste" onPress={() => router.push("/new")} />}
        />
      ) : null}
      {reports.map((r) => (
        <Card key={r.id} onPress={() => router.push({ pathname: "/incident/[id]", params: { id: r.id } })} label={`${r.description}. ${STATUS_LABEL[r.status]}`}>
          <Row style={{ justifyContent: "space-between" }}>
            <Badge label={STATUS_LABEL[r.status]} tone={STATUS_TONE[r.status]} />
            <Muted>{whenLabel(r.occurred_at)}</Muted>
          </Row>
          <Text style={{ ...font.strong, color: colors.ink }} numberOfLines={2}>
            {r.description}
          </Text>
          {r.pincode ? <Muted>{`Pincode ${r.pincode}`}</Muted> : null}
        </Card>
      ))}
    </Screen>
  );
}
