import Ionicons from "@expo/vector-icons/Ionicons";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Animated,
  Image,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type ImageStyle,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import type { Api, Tone } from "@civicloop/core";
import { Spinner } from "./spinner";
import { colors, font, fonts, glass, gradients, radius, shadow, space, TAB_CLEARANCE, TAP, tones } from "./theme";

/** Fill the parent exactly. (React Native 0.88 removed StyleSheet.absoluteFillObject.) */
const FILL = { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 } as const;

/* ---------------------------------------------------------------- backdrop */

/**
 * The colourful page the glass floats over. Glass only looks like glass when there is something to see through it,
 * so soft blobs of orange and blue sit under a gentle blur.
 */
export function Backdrop() {
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <LinearGradient colors={gradients.backdrop} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
      <View style={[styles.blob, { top: -90, right: -70, width: 300, height: 300, backgroundColor: "rgba(255, 122, 56, 0.55)" }]} />
      <View style={[styles.blob, { top: 260, left: -130, width: 340, height: 340, backgroundColor: "rgba(66, 112, 255, 0.38)" }]} />
      <View style={[styles.blob, { bottom: -110, right: -50, width: 300, height: 300, backgroundColor: "rgba(255, 150, 90, 0.45)" }]} />
      <BlurView intensity={34} tint="light" experimentalBlurMethod="dimezisBlurView" style={StyleSheet.absoluteFill} />
    </View>
  );
}

/* ---------------------------------------------------------------- glass */

export function GlassPanel({ children, style, contentStyle, strong, solid }: { children?: ReactNode; style?: StyleProp<ViewStyle>; contentStyle?: StyleProp<ViewStyle>; strong?: boolean; solid?: boolean }) {
  return (
    <View style={[styles.glassShadow, style]}>
      <View style={styles.glassClip}>
        <BlurView intensity={glass.blur} tint="light" experimentalBlurMethod="dimezisBlurView" style={StyleSheet.absoluteFill} />
        <View style={[StyleSheet.absoluteFill, { backgroundColor: solid ? "rgba(255, 255, 255, 0.9)" : strong ? glass.fillStrong : glass.fill }]} />
        <LinearGradient colors={gradients.sheen} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.sheen} pointerEvents="none" />
        <View style={contentStyle}>{children}</View>
      </View>
      <View pointerEvents="none" style={styles.glassBorder} />
    </View>
  );
}

/* ---------------------------------------------------------------- layout */

export function Screen({
  children,
  scroll = true,
  refreshing,
  onRefresh,
  edges = ["top"],
  style,
  tabs,
  header,
}: {
  children: ReactNode;
  /** Pinned above the scrolling content, such as the AppBar. */
  header?: ReactNode;
  scroll?: boolean;
  refreshing?: boolean;
  onRefresh?: () => void;
  edges?: ("top" | "bottom" | "left" | "right")[];
  style?: StyleProp<ViewStyle>;
  /** True on screens that sit above the floating tab bar, so the last item is never hidden behind it. */
  tabs?: boolean;
}) {
  const padding = tabs ? { paddingBottom: TAB_CLEARANCE } : null;
  // Pull down at the top to refresh, with the app's own indicator instead of the system one.
  const scrolledTo = useRef(0);
  const pull = useRef(new Animated.Value(0)).current;
  const latest = useRef({ onRefresh, refreshing });
  latest.current = { onRefresh, refreshing };
  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponderCapture: (_, g) => !!latest.current.onRefresh && !latest.current.refreshing && scrolledTo.current <= 0 && g.dy > 10 && g.dy > Math.abs(g.dx) * 1.5,
      onPanResponderMove: (_, g) => pull.setValue(Math.min(Math.max(g.dy * 0.5, 0), PULL_MAX)),
      onPanResponderRelease: (_, g) => {
        const triggered = g.dy * 0.5 >= PULL_TRIGGER;
        Animated.spring(pull, { toValue: triggered ? PULL_REST : 0, useNativeDriver: true, damping: 20, stiffness: 240 }).start();
        if (triggered) latest.current.onRefresh?.();
      },
      onPanResponderTerminate: () => Animated.spring(pull, { toValue: 0, useNativeDriver: true }).start(),
    }),
  ).current;

  // the indicator stays while a refresh runs, and tucks away when it ends
  useEffect(() => {
    Animated.spring(pull, { toValue: refreshing ? PULL_REST : 0, useNativeDriver: true, damping: 20, stiffness: 240 }).start();
  }, [refreshing, pull]);

  const indicatorOpacity = pull.interpolate({ inputRange: [0, PULL_TRIGGER * 0.6, PULL_REST], outputRange: [0, 0.6, 1], extrapolate: "clamp" });

  return (
    <View style={styles.screen}>
      <Backdrop />
      <SafeAreaView style={{ flex: 1 }} edges={edges}>
        {header}
        {scroll ? (
          <View style={{ flex: 1 }} {...(onRefresh ? pan.panHandlers : {})}>
            {onRefresh ? (
              <Animated.View pointerEvents="none" style={[styles.pullIndicator, { opacity: indicatorOpacity, transform: [{ translateY: Animated.subtract(pull, PULL_REST + 6) }] }]}>
                <GlassPanel strong style={{ borderRadius: radius.pill }} contentStyle={styles.pullBubble}>
                  <Spinner size={22} />
                </GlassPanel>
              </Animated.View>
            ) : null}
            <Animated.View style={{ flex: 1, transform: [{ translateY: pull }] }}>
              <ScrollView
                contentContainerStyle={[styles.content, padding, style]}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator={false}
                automaticallyAdjustKeyboardInsets
                scrollEventThrottle={16}
                onScroll={(e) => {
                  scrolledTo.current = e.nativeEvent.contentOffset.y;
                }}
              >
                {children}
              </ScrollView>
            </Animated.View>
          </View>
        ) : (
          <View style={[styles.content, { flex: 1 }, padding, style]}>{children}</View>
        )}
      </SafeAreaView>
    </View>
  );
}

const PULL_TRIGGER = 56; // how far to drag before letting go refreshes
const PULL_REST = 52; // where the indicator sits while refreshing
const PULL_MAX = 96;

/** A frosted bar at the top of a pushed screen: a round back button and the title. */
export function TopBar({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <GlassPanel style={styles.topBar} contentStyle={styles.topBarRow} strong>
      <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="Go back" hitSlop={10} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}>
        <Ionicons name="chevron-back" size={22} color={colors.ink} />
      </Pressable>
      <Text style={styles.topBarTitle} accessibilityRole="header" numberOfLines={1}>
        {title}
      </Text>
    </GlassPanel>
  );
}

export function Title({ children }: { children: ReactNode }) {
  return (
    <Text style={styles.title} accessibilityRole="header">
      {children}
    </Text>
  );
}

export function Heading({ children }: { children: ReactNode }) {
  return (
    <Text style={styles.heading} accessibilityRole="header">
      {children}
    </Text>
  );
}

export function Body({ children, style }: { children: ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[styles.body, style]}>{children}</Text>;
}

export function Muted({ children }: { children: ReactNode }) {
  return <Text style={styles.muted}>{children}</Text>;
}

export function Gap({ size = "md" }: { size?: keyof typeof space }) {
  return <View style={{ height: space[size] }} />;
}

export function Row({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.row, style]}>{children}</View>;
}

export function Card({ children, onPress, style, label }: { children: ReactNode; onPress?: () => void; style?: StyleProp<ViewStyle>; label?: string }) {
  const body = (
    <GlassPanel style={style} contentStyle={styles.cardBody}>
      {children}
    </GlassPanel>
  );
  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label} style={({ pressed }) => pressed && styles.pressed}>
      {body}
    </Pressable>
  );
}

/* ---------------------------------------------------------------- controls */

export function Button({
  label,
  onPress,
  variant = "primary",
  busy,
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  busy?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const off = disabled || busy;
  const primary = variant === "primary";
  const textColor = primary ? "#ffffff" : variant === "danger" ? colors.bad : variant === "ghost" ? colors.accentDark : colors.ink;
  const content = (
    <>
      {busy ? <Spinner size={20} color={textColor} /> : null}
      <Text style={[styles.buttonText, { color: textColor }, primary && styles.buttonTextOnColour]}>{label}</Text>
    </>
  );
  return (
    <Pressable
      onPress={onPress}
      disabled={off}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      style={({ pressed }) => [styles.buttonOuter, primary && !off && shadow.glow, off && styles.disabled, pressed && styles.pressed, style]}
    >
      {primary ? (
        <LinearGradient colors={gradients.accent} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.buttonFill}>
          <LinearGradient colors={gradients.gloss} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.gloss} pointerEvents="none" />
          <View pointerEvents="none" style={styles.rim} />
          {content}
        </LinearGradient>
      ) : variant === "ghost" ? (
        <View style={styles.buttonFill}>{content}</View>
      ) : (
        <View style={[styles.buttonFill, styles.buttonGlass, variant === "danger" && { borderColor: "rgba(192, 50, 42, 0.5)" }]}>{content}</View>
      )}
    </Pressable>
  );
}

export function Field({ label, error, hint, style, ...input }: TextInputProps & { label: string; error?: string | null; hint?: string }) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        placeholderTextColor={colors.faint}
        accessibilityLabel={label}
        {...input}
        onFocus={(e) => {
          setFocused(true);
          input.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          input.onBlur?.(e);
        }}
        style={[styles.input, focused && styles.inputFocused, !!error && { borderColor: colors.bad }, input.multiline && styles.multiline, style]}
      />
      {error ? (
        <Text style={[styles.hint, { color: colors.bad }]} accessibilityRole="alert">
          {error}
        </Text>
      ) : hint ? (
        <Text style={styles.hint}>{hint}</Text>
      ) : null}
    </View>
  );
}

export function Chip({ label, selected, onPress }: { label: string; selected?: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!selected }} style={({ pressed }) => [pressed && styles.pressed]}>
      <View style={[styles.chip, selected && styles.chipSelected]}>
        {selected ? <LinearGradient colors={gradients.accentSoft} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={StyleSheet.absoluteFill} /> : null}
        <Text style={[styles.chipText, selected && { color: colors.accentDark }]}>{label}</Text>
      </View>
    </Pressable>
  );
}

export function Badge({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  const t = tones[tone];
  return (
    <View style={[styles.badge, { backgroundColor: t.bg }]} accessible accessibilityLabel={label}>
      <View style={[styles.badgeDot, { backgroundColor: t.fg, shadowColor: t.fg }]} />
      <Text style={[styles.badgeText, { color: t.fg }]}>{label}</Text>
    </View>
  );
}

export function Banner({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  const t = tones[tone];
  return (
    <View style={[styles.banner, { backgroundColor: t.bg, borderColor: t.fg + "55" }]} accessibilityRole={tone === "bad" ? "alert" : undefined}>
      <Text style={[styles.bannerText, { color: t.fg }]}>{children}</Text>
    </View>
  );
}

export function Empty({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <GlassPanel contentStyle={styles.empty}>
      <Text style={styles.heading}>{title}</Text>
      {text ? <Text style={[styles.muted, { textAlign: "center" }]}>{text}</Text> : null}
      {action}
    </GlassPanel>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <View style={styles.loading} accessibilityLabel={label}>
      <Spinner size={34} />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

/** The app mark: a glossy orange rounded square with the loop arrow. */
export function BrandMark({ size = 64 }: { size?: number }) {
  return (
    <View style={[{ width: size, height: size, borderRadius: size * 0.3 }, shadow.glow]} accessibilityLabel="CivicLoop">
      <LinearGradient colors={gradients.accent} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={{ flex: 1, borderRadius: size * 0.3, alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
        <LinearGradient colors={gradients.gloss} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={{ position: "absolute", top: 0, left: 0, right: 0, height: "52%" }} pointerEvents="none" />
        <Ionicons name="refresh" size={size * 0.55} color="#ffffff" />
      </LinearGradient>
    </View>
  );
}

/* ---------------------------------------------------------------- tab bar */

/** The floating frosted tab bar. Spread the result into the Tabs `screenOptions`. */
export function useFloatingTabBar() {
  const insets = useSafeAreaInsets();
  return {
    headerShown: false,
    tabBarActiveTintColor: colors.accent,
    tabBarInactiveTintColor: colors.faint,
    tabBarLabelStyle: { fontFamily: fonts.semibold, fontSize: 11, marginBottom: 2 },
    tabBarItemStyle: { paddingTop: 8 },
    tabBarBackground: () => (
      <View style={styles.tabBackground}>
        <BlurView intensity={70} tint="light" experimentalBlurMethod="dimezisBlurView" style={StyleSheet.absoluteFill} />
        <View style={[StyleSheet.absoluteFill, { backgroundColor: "rgba(255,255,255,0.5)" }]} />
        <LinearGradient colors={gradients.sheen} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.sheen} pointerEvents="none" />
        <View pointerEvents="none" style={styles.tabBorder} />
      </View>
    ),
    tabBarStyle: {
      position: "absolute" as const,
      left: 18,
      right: 18,
      bottom: Math.max(insets.bottom, 12) + 4,
      height: 70,
      borderRadius: radius.xl,
      borderTopWidth: 0,
      backgroundColor: "transparent",
      ...shadow.float,
    },
  };
}

/* ---------------------------------------------------------------- photos */

export function PhotoStrip({ photos, onRemove }: { photos: { uri: string }[]; onRemove?: (index: number) => void }) {
  if (photos.length === 0) return null;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.md, paddingVertical: 2 }}>
      {photos.map((photo, index) => (
        <View key={`${photo.uri}-${index}`} style={styles.photoWrap}>
          <Image source={{ uri: photo.uri }} style={styles.photo} accessibilityLabel={`Photo ${index + 1}`} />
          {onRemove ? (
            <Pressable onPress={() => onRemove(index)} accessibilityRole="button" accessibilityLabel={`Remove photo ${index + 1}`} style={styles.photoRemove} hitSlop={8}>
              <Ionicons name="close" size={16} color={colors.ink} />
            </Pressable>
          ) : null}
        </View>
      ))}
    </ScrollView>
  );
}

/** A photo the server holds. The image request has to carry the sign-in, so it is built here. */
export function ServerImage({ api, assetId, style, label }: { api: Api; assetId: string; style?: StyleProp<ImageStyle>; label: string }) {
  const [source, setSource] = useState<{ uri: string; headers?: Record<string, string> } | null>(null);
  useEffect(() => {
    let live = true;
    let objectUrl: string | null = null;
    void api.authHeaders().then(async (headers) => {
      if (!live) return;
      if (Platform.OS !== "web") return setSource({ uri: api.mediaUrl(assetId), headers });
      // a browser cannot add headers to an image request, so it fetches the picture itself
      try {
        const response = await fetch(api.mediaUrl(assetId), { headers });
        if (!response.ok) return;
        objectUrl = URL.createObjectURL(await response.blob());
        if (live) setSource({ uri: objectUrl });
      } catch {
        /* the grey box stays */
      }
    });
    return () => {
      live = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, assetId]);
  if (!source) return <View style={[styles.photo, style as object, { backgroundColor: colors.sunken }]} />;
  return <Image source={source} style={[styles.photo, style]} accessibilityLabel={label} />;
}

/* ---------------------------------------------------------------- styles */

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, gap: space.lg, paddingBottom: space.xxl },
  blob: { position: "absolute", borderRadius: 999 },
  pullIndicator: { position: "absolute", top: 0, left: 0, right: 0, alignItems: "center", zIndex: 5 },
  pullBubble: { width: 46, height: 46, alignItems: "center", justifyContent: "center" },

  title: { ...font.title, color: colors.ink },
  heading: { ...font.heading, color: colors.ink },
  body: { ...font.body, color: colors.text },
  muted: { ...font.small, color: colors.muted },
  row: { flexDirection: "row", alignItems: "center", gap: space.md },

  glassShadow: { borderRadius: radius.lg, ...shadow.card },
  glassClip: { borderRadius: radius.lg, overflow: "hidden" },
  glassBorder: { ...FILL, borderRadius: radius.lg, borderWidth: 1.2, borderColor: glass.border },
  sheen: { position: "absolute", top: 0, left: 0, right: 0, height: "55%" },
  cardBody: { padding: space.lg, gap: space.sm },
  pressed: { opacity: 0.88, transform: [{ scale: 0.985 }] },
  disabled: { opacity: 0.5 },

  topBar: { borderRadius: radius.pill },
  topBarRow: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: 8, paddingLeft: 8, paddingRight: 20 },
  backButton: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.85)", borderWidth: 1, borderColor: glass.border },
  topBarTitle: { ...font.strong, color: colors.ink, flex: 1 },

  buttonOuter: { borderRadius: radius.pill },
  buttonFill: { minHeight: TAP, paddingHorizontal: space.xl, borderRadius: radius.pill, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: space.sm, overflow: "hidden" },
  buttonGlass: { backgroundColor: glass.fillStrong, borderWidth: 1.2, borderColor: "rgba(15, 27, 61, 0.12)" },
  gloss: { position: "absolute", top: 0, left: 0, right: 0, height: "52%" },
  rim: { ...FILL, borderRadius: radius.pill, borderWidth: 1.2, borderColor: "rgba(255,255,255,0.5)" },
  buttonText: { ...font.strong, fontFamily: fonts.semibold },
  buttonTextOnColour: { textShadowColor: "rgba(120, 40, 0, 0.35)", textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 2 },

  field: { gap: 6 },
  label: { ...font.label, color: colors.ink },
  input: {
    minHeight: TAP,
    borderWidth: 1.2,
    borderColor: "rgba(15, 27, 61, 0.10)",
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    backgroundColor: "rgba(244, 246, 253, 0.8)",
    ...font.body,
    color: colors.text,
    shadowColor: "#1a2a66",
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
  },
  inputFocused: { borderColor: colors.accent, backgroundColor: "rgba(255,255,255,0.92)", shadowColor: colors.accent, shadowOpacity: 0.25, shadowRadius: 12 },
  multiline: { minHeight: 112, textAlignVertical: "top" },
  hint: { ...font.small, color: colors.muted },

  chip: { minHeight: 40, paddingHorizontal: space.lg, borderRadius: radius.pill, borderWidth: 1.2, borderColor: "rgba(15, 27, 61, 0.10)", backgroundColor: "rgba(255,255,255,0.7)", alignItems: "center", justifyContent: "center", overflow: "hidden" },
  chipSelected: { borderColor: "rgba(236, 95, 31, 0.7)", backgroundColor: "rgba(255,255,255,0.85)" },
  chipText: { ...font.label, color: colors.muted },

  badge: { flexDirection: "row", alignItems: "center", gap: 7, alignSelf: "flex-start", paddingHorizontal: 12, paddingVertical: 5, borderRadius: radius.pill },
  badgeDot: { width: 7, height: 7, borderRadius: 4, shadowOpacity: 0.7, shadowRadius: 4, shadowOffset: { width: 0, height: 0 } },
  badgeText: { fontFamily: fonts.semibold, fontSize: 12, lineHeight: 16 },
  banner: { borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.lg, paddingVertical: space.md },
  bannerText: { ...font.small, fontFamily: fonts.medium },

  empty: { alignItems: "center", gap: space.sm, paddingVertical: space.xxl, paddingHorizontal: space.xl },
  loading: { alignItems: "center", gap: space.sm, paddingVertical: space.xxl },

  tabBackground: { ...FILL, borderRadius: radius.xl, overflow: "hidden" },
  tabBorder: { ...FILL, borderRadius: radius.xl, borderWidth: 1.2, borderColor: glass.border },

  photoWrap: { borderRadius: radius.md, ...shadow.card },
  photo: { width: 128, height: 128, borderRadius: radius.md, backgroundColor: colors.sunken, borderWidth: 2, borderColor: "rgba(255,255,255,0.9)" },
  photoRemove: { position: "absolute", top: 8, right: 8, width: 28, height: 28, borderRadius: 14, backgroundColor: "rgba(255,255,255,0.92)", alignItems: "center", justifyContent: "center" },
});
