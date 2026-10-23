import { Stack } from "expo-router";
import { colors } from "@civicloop/ui";

export default function AppLayout() {
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }} />;
}
