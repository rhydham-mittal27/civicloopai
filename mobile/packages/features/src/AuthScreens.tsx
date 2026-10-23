import { router } from "expo-router";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { normaliseServerUrl } from "@civicloop/core";
import { TabHeader } from "./TabHeader";
import { Banner, BrandMark, Body, Button, Card, Field, Gap, Muted, Screen, Title, TopBar, colors, font, fonts, space, useAction, useDialog, useSession } from "@civicloop/ui";

/** Sign in. The crew app has no sign-up: crew accounts are made by a city admin. */
export function LoginScreen({ appName, tagline, canRegister }: { appName: string; tagline: string; canRegister: boolean }) {
  const { signIn, serverUrl } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  return (
    <Screen edges={["top", "bottom"]}>
      <Gap size="xl" />
      <View style={{ alignItems: "center", gap: space.md, paddingHorizontal: space.lg }}>
        <BrandMark size={76} />
        <Text style={{ fontFamily: fonts.bold, fontSize: 30, lineHeight: 38, letterSpacing: -0.6, color: colors.ink, textAlign: "center" }} accessibilityRole="header">
          {appName}
        </Text>
        <Body style={{ textAlign: "center", color: colors.muted }}>{tagline}</Body>
      </View>
      <Gap />
      <Card>
        {!serverUrl ? <Banner tone="warn">Set the server address first, so the app knows where to sign in.</Banner> : null}
        <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" autoComplete="email" keyboardType="email-address" textContentType="username" />
        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password" textContentType="password" />
        {error ? <Banner tone="bad">{error}</Banner> : null}
        <Button label="Sign in" busy={busy === "login"} disabled={!email.trim() || !password || !serverUrl} onPress={() => run("login", () => signIn(email, password))} />
      </Card>
      {canRegister ? <Button label="Create an account" variant="secondary" onPress={() => router.push("/register")} /> : <Muted>Crew accounts are created by your city admin. Ask them if you cannot sign in.</Muted>}
      <Pressable onPress={() => router.push("/server")} accessibilityRole="button" hitSlop={10} style={{ alignSelf: "center", padding: space.md }}>
        <Text style={{ ...font.small, color: colors.muted }}>{serverUrl ? `Server: ${serverUrl}` : "Set server address"}</Text>
      </Pressable>
    </Screen>
  );
}

/** Where the app talks to. Needed while the server is on a laptop on the same Wi-Fi. */
export function ServerScreen() {
  const { api, serverUrl, setServerUrl } = useSession();
  const [value, setValue] = useState(serverUrl);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const { busy, run } = useAction();

  const test = () =>
    run("test", async () => {
      await setServerUrl(value);
      const ok = await api.ping();
      setResult(ok ? { ok, text: "Connected. The server answered." } : { ok, text: "No answer. Check the address, that the server is running, and that your phone is on the same Wi-Fi." });
    });

  return (
    <Screen>
      <TopBar title="Server address" onBack={() => router.back()} />
      <Title>Server address</Title>
      <Body>Where the CivicLoop server is running. For a test on your own network this looks like http://192.168.1.20:8000.</Body>
      <Card>
        <Field label="Address" value={value} onChangeText={setValue} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="http://192.168.1.20:8000" hint={value ? `Will use ${normaliseServerUrl(value)}` : undefined} />
        {result ? <Banner tone={result.ok ? "good" : "bad"}>{result.text}</Banner> : null}
        <Button label="Test connection" variant="secondary" busy={busy === "test"} disabled={!value.trim()} onPress={test} />
        <Button
          label="Save"
          disabled={!value.trim()}
          onPress={async () => {
            await setServerUrl(value);
            router.back();
          }}
        />
      </Card>
    </Screen>
  );
}

export function AccountScreen({ roleLabel, children }: { roleLabel: string; children?: React.ReactNode }) {
  const { me, serverUrl, signOut } = useSession();
  const dialog = useDialog();
  return (
    <Screen tabs header={<TabHeader title="Account" />}>
      <Card>
        <Text style={{ ...font.heading, color: colors.ink }}>{me?.name ?? roleLabel}</Text>
        <Muted>{me?.email ?? ""}</Muted>
        <Muted>{me ? `${roleLabel} · ${me.city}${me.pincode ? ` · ${me.pincode}` : ""}` : roleLabel}</Muted>
      </Card>
      {children}
      <Card>
        <Muted>Server</Muted>
        <Body>{serverUrl || "Not set"}</Body>
        <Button label="Change server address" variant="secondary" onPress={() => router.push("/server")} />
      </Card>
      <Button
        label="Sign out"
        variant="danger"
        onPress={async () => {
          const yes = await dialog.confirm({ title: "Sign out?", message: "You will need your email and password to sign in again.", confirmLabel: "Sign out", cancelLabel: "Stay signed in", tone: "warn", icon: "log-out", danger: true });
          if (yes) await signOut();
        }}
      />
    </Screen>
  );
}
