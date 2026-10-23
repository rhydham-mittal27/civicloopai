import { router } from "expo-router";
import { NotFoundScreen } from "@civicloop/ui";

export default function NotFound() {
  return <NotFoundScreen onHome={() => router.replace("/")} />;
}
