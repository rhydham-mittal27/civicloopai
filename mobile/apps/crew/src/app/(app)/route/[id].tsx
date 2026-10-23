import { useLocalSearchParams } from "expo-router";
import { RouteScreen } from "@/screens/Route";

export default function Route() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <RouteScreen routeId={id} />;
}
