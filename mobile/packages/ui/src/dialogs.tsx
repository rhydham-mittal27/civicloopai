import Ionicons from "@expo/vector-icons/Ionicons";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Animated, BackHandler, Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { Tone } from "@civicloop/core";
import { Button, GlassPanel } from "./components";
import { colors, font, fonts, gradients, shadow, space, tones } from "./theme";

/**
 * The app's own dialogs. Nothing in the app opens a system alert: every question, warning and choice is one of these,
 * drawn in the same glass style. They are promises, so a screen can simply `await dialog.confirm(...)`.
 */

type IconName = keyof typeof Ionicons.glyphMap;

export interface DialogAction {
  label: string;
  value: string;
  tone?: "primary" | "secondary" | "danger" | "ghost";
}

interface Spec {
  kind: "dialog" | "sheet";
  title: string;
  message?: string;
  icon?: IconName;
  tone?: Tone;
  actions: DialogAction[];
  /** What closing without choosing (tapping outside, or the back button) resolves to. null means it cannot be dismissed that way. */
  dismissValue: string | null | undefined;
  resolve: (value: string | null) => void;
}

export interface DialogApi {
  /** A yes/no question. Resolves true on the confirm button. */
  confirm: (o: { title: string; message?: string; confirmLabel?: string; cancelLabel?: string; tone?: Tone; icon?: IconName; danger?: boolean }) => Promise<boolean>;
  /** A notice with one button. */
  alert: (o: { title: string; message?: string; okLabel?: string; tone?: Tone; icon?: IconName }) => Promise<void>;
  /** A bottom sheet of choices. Resolves with the chosen value, or null if dismissed. */
  choose: (o: { title: string; message?: string; options: DialogAction[]; cancelLabel?: string }) => Promise<string | null>;
  /** Explains why something is needed, and returns true if the person wants to carry on to the system permission prompt. */
  explain: (o: { title: string; message: string; icon?: IconName; continueLabel?: string }) => Promise<boolean>;
  /** The system will not ask again, so the only way is the phone's settings. Offers to open them. */
  openSettingsFor: (o: { title: string; message: string; icon?: IconName }) => Promise<void>;
}

const DialogContext = createContext<DialogApi | null>(null);

const DEFAULT_ICON: Record<Tone, IconName> = {
  neutral: "help-circle",
  info: "information-circle",
  warn: "alert-circle",
  good: "checkmark-circle",
  bad: "warning",
};

export function DialogProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<Spec[]>([]);
  const current = queue[0] ?? null;

  const push = useCallback(
    (spec: Omit<Spec, "resolve">) =>
      new Promise<string | null>((resolve) => {
        setQueue((q) => [...q, { ...spec, resolve }]);
      }),
    [],
  );

  const api = useMemo<DialogApi>(
    () => ({
      confirm: async ({ title, message, confirmLabel = "Continue", cancelLabel = "Cancel", tone = "neutral", icon, danger }) => {
        const picked = await push({
          kind: "dialog",
          title,
          message,
          tone,
          icon,
          actions: [
            { label: confirmLabel, value: "yes", tone: danger ? "danger" : "primary" },
            { label: cancelLabel, value: "no", tone: "secondary" },
          ],
          dismissValue: "no",
        });
        return picked === "yes";
      },
      alert: async ({ title, message, okLabel = "OK", tone = "info", icon }) => {
        await push({ kind: "dialog", title, message, tone, icon, actions: [{ label: okLabel, value: "ok", tone: "primary" }], dismissValue: "ok" });
      },
      choose: ({ title, message, options, cancelLabel = "Cancel" }) =>
        push({ kind: "sheet", title, message, actions: [...options, { label: cancelLabel, value: "__cancel", tone: "secondary" }], dismissValue: null }).then((v) => (v === "__cancel" ? null : v)),
      explain: async ({ title, message, icon, continueLabel = "Continue" }) => {
        const picked = await push({
          kind: "dialog",
          title,
          message,
          tone: "info",
          icon,
          actions: [
            { label: continueLabel, value: "yes", tone: "primary" },
            { label: "Not now", value: "no", tone: "ghost" },
          ],
          dismissValue: "no",
        });
        return picked === "yes";
      },
      openSettingsFor: async ({ title, message, icon }) => {
        const picked = await push({
          kind: "dialog",
          title,
          message,
          tone: "warn",
          icon,
          actions: [
            { label: "Open settings", value: "settings", tone: "primary" },
            { label: "Not now", value: "no", tone: "ghost" },
          ],
          dismissValue: "no",
        });
        if (picked === "settings") await Linking.openSettings().catch(() => {});
      },
    }),
    [push],
  );

  return (
    <DialogContext value={api}>
      {children}
      {current ? <DialogView key={queue.length + current.title} spec={current} onDone={(v) => { current.resolve(v); setQueue((q) => q.slice(1)); }} /> : null}
    </DialogContext>
  );
}

export function useDialog(): DialogApi {
  const value = useContext(DialogContext);
  if (!value) throw new Error("useDialog must be used inside a DialogProvider");
  return value;
}

function DialogView({ spec, onDone }: { spec: Spec; onDone: (value: string | null) => void }) {
  const insets = useSafeAreaInsets();
  const enter = useRef(new Animated.Value(0)).current;
  const closing = useRef(false);

  useEffect(() => {
    Animated.spring(enter, { toValue: 1, damping: 18, stiffness: 220, mass: 0.9, useNativeDriver: true }).start();
  }, [enter]);

  const close = useCallback(
    (value: string | null) => {
      if (closing.current) return;
      closing.current = true;
      Animated.timing(enter, { toValue: 0, duration: 150, useNativeDriver: true }).start(() => onDone(value));
    },
    [enter, onDone],
  );

  const dismiss = spec.dismissValue;
  const canDismiss = dismiss !== null && dismiss !== undefined;

  // the phone's back button closes a dismissible dialog instead of leaving the screen behind it
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (canDismiss) close(dismiss as string);
      return true;
    });
    return () => sub.remove();
  }, [canDismiss, close, dismiss]);

  const tone = spec.tone ?? "neutral";
  const palette = tones[tone];
  const sheet = spec.kind === "sheet";
  const translateY = enter.interpolate({ inputRange: [0, 1], outputRange: [sheet ? 80 : 18, 0] });
  const scale = enter.interpolate({ inputRange: [0, 1], outputRange: [sheet ? 1 : 0.94, 1] });

  return (
    <View style={styles.root} accessibilityViewIsModal importantForAccessibility="yes">
      <Animated.View style={[StyleSheet.absoluteFill, { opacity: enter }]}>
        <BlurView intensity={26} tint="dark" experimentalBlurMethod="dimezisBlurView" style={StyleSheet.absoluteFill} />
        <Pressable style={[StyleSheet.absoluteFill, { backgroundColor: colors.overlay }]} onPress={() => canDismiss && close(dismiss as string)} accessibilityLabel="Dismiss" accessibilityRole="button" disabled={!canDismiss} />
      </Animated.View>
      <View style={[styles.holder, sheet ? { justifyContent: "flex-end", paddingBottom: Math.max(insets.bottom, 12) + 8 } : { justifyContent: "center" }]} pointerEvents="box-none">
        <Animated.View style={{ opacity: enter, transform: [{ translateY }, { scale }] }} accessibilityRole="alert">
          <GlassPanel solid style={shadow.float} contentStyle={styles.panel}>
            {!sheet ? (
              <View style={[styles.bubble, { backgroundColor: palette.bg }]}>
                <LinearGradient colors={gradients.sheen} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={StyleSheet.absoluteFill} />
                <Ionicons name={spec.icon ?? DEFAULT_ICON[tone]} size={30} color={palette.fg} />
              </View>
            ) : null}
            <Text style={[styles.title, sheet && { textAlign: "left" }]} accessibilityRole="header">
              {spec.title}
            </Text>
            {spec.message ? <Text style={[styles.message, sheet && { textAlign: "left" }]}>{spec.message}</Text> : null}
            <View style={styles.actions}>
              {spec.actions.map((action) => (
                <Button key={action.value} label={action.label} variant={action.tone ?? "secondary"} onPress={() => close(action.value)} />
              ))}
            </View>
          </GlassPanel>
        </Animated.View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, zIndex: 1000, elevation: 1000 },
  holder: { flex: 1, paddingHorizontal: space.xl },
  panel: { padding: space.xl, gap: space.md, alignItems: "stretch" },
  bubble: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", alignSelf: "center", overflow: "hidden", borderWidth: 1.2, borderColor: "rgba(255,255,255,0.9)" },
  title: { ...font.heading, fontFamily: fonts.semibold, color: colors.ink, textAlign: "center", fontSize: 19, lineHeight: 27 },
  message: { ...font.body, color: colors.muted, textAlign: "center" },
  actions: { gap: space.sm, marginTop: space.sm },
});

