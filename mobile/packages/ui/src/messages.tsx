import { Text, View } from "react-native";
import { BrandMark, Body, Button, Card, Muted, Screen } from "./components";
import { colors, fonts, space } from "./theme";

/**
 * Full-screen messages in the app's own style, used where Expo Router would otherwise show its built-in
 * "Unmatched Route" and crash screens. They need no sign-in and no dialogs, so they work even when the app itself failed.
 */
function Centered({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Screen scroll={false} edges={["top", "bottom"]} style={{ justifyContent: "center" }}>
      <View style={{ alignItems: "center", gap: space.md, marginBottom: space.md }}>
        <BrandMark size={72} />
        <Text style={{ fontFamily: fonts.bold, fontSize: 26, lineHeight: 34, letterSpacing: -0.4, color: colors.ink, textAlign: "center" }} accessibilityRole="header">
          {title}
        </Text>
      </View>
      {children}
    </Screen>
  );
}

export function NotFoundScreen({ onHome }: { onHome: () => void }) {
  return (
    <Centered title="That page is not here">
      <Card>
        <Body style={{ textAlign: "center" }}>The link may be old or mistyped. Nothing is wrong with your account.</Body>
        <Button label="Go to the start" onPress={onHome} />
      </Card>
    </Centered>
  );
}

export function ErrorScreen({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <Centered title="Something went wrong">
      <Card>
        <Body style={{ textAlign: "center" }}>The app hit a problem it could not recover from. Your reports and jobs are safe on the server.</Body>
        {message ? <Muted>{message}</Muted> : null}
        <Button label="Try again" onPress={onRetry} />
      </Card>
    </Centered>
  );
}
