import { Stack, type ErrorBoundaryProps } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { DialogProvider, ErrorScreen, Loading, Screen, SessionProvider, colors, useBrandFonts, useSession } from "@civicloop/ui";
// Registers the background location task as soon as the app JavaScript loads, which is when the system wakes it headless.
import "@/location/sharing";

/** Shown if the app crashes, in place of the router's built-in error screen. */
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  return <ErrorScreen message={error.message} onRetry={retry} />;
}

export default function RootLayout() {
  return (
    <SessionProvider expectedRole="sanitation_worker" roleName="sanitation crews" defaultServer={process.env.EXPO_PUBLIC_API_URL}>
      <StatusBar style="dark" />
      <DialogProvider>
        <Gate />
      </DialogProvider>
    </SessionProvider>
  );
}

function Gate() {
  const { status } = useSession();
  const fontsReady = useBrandFonts();
  if (status === "loading" || !fontsReady) {
    return (
      <Screen scroll={false}>
        <Loading label="Starting CivicLoop Crew" />
      </Screen>
    );
  }
  const signedIn = status === "signedIn";
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }}>
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
      <Stack.Screen name="welcome" />
      <Stack.Screen name="server" />
    </Stack>
  );
}
