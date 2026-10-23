import { useLocalSearchParams } from "expo-router";
import { IncidentDetail } from "@civicloop/features";

export default function ReportDetail() {
  const { id, notice } = useLocalSearchParams<{ id: string; notice?: string }>();
  return <IncidentDetail id={id} notice={notice} canAddPhoto />;
}
