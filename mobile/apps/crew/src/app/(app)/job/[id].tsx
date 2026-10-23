import { useLocalSearchParams } from "expo-router";
import { JobDetailScreen } from "@/screens/JobDetail";

export default function Job() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <JobDetailScreen orderId={id} />;
}
