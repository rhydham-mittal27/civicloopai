import Ionicons from "@expo/vector-icons/Ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { useCallback, useEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import { Animated, Pressable, StyleSheet, Text, View, useWindowDimensions, type NativeScrollEvent, type NativeSyntheticEvent } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { BrandMark, Button, GlassPanel } from "./components";
import { loadFlag, saveFlag } from "./storage";
import { colors, fonts, gradients, radius, shadow, space } from "./theme";

type IconName = ComponentProps<typeof Ionicons>["name"];

/* ---------------------------------------------------------------- app bar */

/** First letters of a name, for the round profile button. */
export function initialsOf(name: string | undefined | null): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

/**
 * The bar pinned at the top of every main screen: the brand mark, where you are, and a round profile button.
 * `right` is for one extra action (a refresh, a status dot); the profile button always opens the account page.
 */
export function AppBar({ title, subtitle, name, onProfile, right }: { title: string; subtitle?: string; name?: string | null; onProfile: () => void; right?: ReactNode }) {
  return (
    <View style={styles.barWrap}>
      <GlassPanel strong contentStyle={styles.bar}>
        <BrandMark size={38} />
        <View style={{ flex: 1 }}>
          <Text style={styles.barTitle} numberOfLines={1} accessibilityRole="header">
            {title}
          </Text>
          {subtitle ? (
            <Text style={styles.barSub} numberOfLines={1}>
              {subtitle}
            </Text>
          ) : null}
        </View>
        {right}
        <Pressable onPress={onProfile} accessibilityRole="button" accessibilityLabel={`Your account${name ? `, ${name}` : ""}`} hitSlop={8} style={({ pressed }) => [pressed && { opacity: 0.8, transform: [{ scale: 0.95 }] }]}>
          <LinearGradient colors={["#33427a", "#0f1b3d"]} start={{ x: 0.2, y: 0 }} end={{ x: 0.8, y: 1 }} style={styles.avatar}>
            <Text style={styles.avatarText}>{initialsOf(name)}</Text>
          </LinearGradient>
        </Pressable>
      </GlassPanel>
    </View>
  );
}

/* ---------------------------------------------------------------- tab icons */

/**
 * An icon for the floating tab bar. The active tab gets the filled icon on a soft orange pill;
 * a `raised` tab (the main action) is a glossy orange button that rises above the bar.
 */
export function TabIcon({ name, focused, color, raised }: { name: string; focused: boolean; color: string; raised?: boolean }) {
  const glyph = (focused || raised ? name : `${name}-outline`) as IconName;
  const lift = useRef(new Animated.Value(focused ? 1 : 0)).current;
  useEffect(() => {
    Animated.spring(lift, { toValue: focused ? 1 : 0, useNativeDriver: true, damping: 16, stiffness: 220 }).start();
  }, [focused, lift]);
  if (raised) {
    return (
      <View style={[styles.raised, shadow.glow]}>
        <LinearGradient colors={gradients.accent} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.raisedFace}>
          <LinearGradient colors={gradients.gloss} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.raisedGloss} pointerEvents="none" />
          <Ionicons name={glyph} size={28} color="#ffffff" />
        </LinearGradient>
      </View>
    );
  }
  return (
    <View style={styles.tabSlot}>
      <Animated.View style={[styles.pill, { opacity: lift, transform: [{ scaleX: lift.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1] }) }] }]} />
      <Ionicons name={glyph} size={23} color={focused ? colors.accent : color} />
    </View>
  );
}

/* ---------------------------------------------------------------- intro */

export interface IntroSlide {
  icon: IconName;
  /** Two small icons that float beside the main one. */
  accents?: [IconName, IconName];
  title: string;
  text: string;
}

/** Remembers whether the welcome screens were seen on this phone. `seen` is null until that is known. */
export function useIntro(app: string): { seen: boolean | null; finish: () => void; replay: () => void } {
  const [seen, setSeen] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    void loadFlag(`intro.${app}`).then((value) => live && setSeen(value));
    return () => {
      live = false;
    };
  }, [app]);
  const finish = useCallback(() => {
    setSeen(true);
    void saveFlag(`intro.${app}`, true);
  }, [app]);
  const replay = useCallback(() => {
    setSeen(false);
    void saveFlag(`intro.${app}`, false);
  }, [app]);
  return { seen, finish, replay };
}

/** Swipeable welcome screens shown the first time the app opens. */
export function Intro({ slides, appName, onDone }: { slides: IntroSlide[]; appName: string; onDone: () => void }) {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const scroller = useRef<{ scrollTo: (to: { x: number; animated: boolean }) => void } | null>(null);
  const x = useRef(new Animated.Value(0)).current;
  const [index, setIndex] = useState(0);
  const last = index === slides.length - 1;

  const go = (to: number) => {
    scroller.current?.scrollTo({ x: to * width, animated: true });
    setIndex(to);
  };
  const settle = (e: NativeSyntheticEvent<NativeScrollEvent>) => setIndex(Math.round(e.nativeEvent.contentOffset.x / width));

  return (
    <View style={styles.introRoot}>
      <LinearGradient colors={gradients.backdrop} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
      <View style={[styles.blob, { top: -80, right: -60, width: 300, height: 300, backgroundColor: "rgba(255, 122, 56, 0.5)" }]} />
      <View style={[styles.blob, { bottom: 120, left: -120, width: 320, height: 320, backgroundColor: "rgba(66, 112, 255, 0.34)" }]} />

      <View style={[styles.introTop, { paddingTop: insets.top + space.md }]}>
        <View style={styles.introBrand}>
          <BrandMark size={34} />
          <Text style={styles.introName}>{appName}</Text>
        </View>
        {!last ? (
          <Pressable onPress={onDone} accessibilityRole="button" accessibilityLabel="Skip the introduction" hitSlop={12}>
            <Text style={styles.skip}>Skip</Text>
          </Pressable>
        ) : null}
      </View>

      <Animated.ScrollView
        ref={scroller as never}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={Animated.event([{ nativeEvent: { contentOffset: { x } } }], { useNativeDriver: true })}
        onMomentumScrollEnd={settle}
        scrollEventThrottle={16}
        style={{ flex: 1 }}
      >
        {slides.map((slide, i) => {
          const range = [(i - 1) * width, i * width, (i + 1) * width];
          const float = x.interpolate({ inputRange: range, outputRange: [60, 0, -60], extrapolate: "clamp" });
          const fade = x.interpolate({ inputRange: range, outputRange: [0, 1, 0], extrapolate: "clamp" });
          return (
            <View key={slide.title} style={[styles.slide, { width }]} accessible accessibilityLabel={`${slide.title}. ${slide.text}`}>
              <Animated.View style={[styles.orbWrap, { opacity: fade, transform: [{ translateX: float }] }]}>
                <GlassPanel strong style={styles.orb} contentStyle={styles.orbInner}>
                  <LinearGradient colors={gradients.accent} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.orbCore}>
                    <LinearGradient colors={gradients.gloss} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.raisedGloss} pointerEvents="none" />
                    <Ionicons name={slide.icon} size={64} color="#ffffff" />
                  </LinearGradient>
                </GlassPanel>
                {slide.accents ? (
                  <>
                    <View style={[styles.chip, { top: 8, right: 4 }]}>
                      <Ionicons name={slide.accents[0]} size={22} color={colors.info} />
                    </View>
                    <View style={[styles.chip, { bottom: 14, left: 0 }]}>
                      <Ionicons name={slide.accents[1]} size={22} color={colors.good} />
                    </View>
                  </>
                ) : null}
              </Animated.View>
              <Animated.View style={{ opacity: fade, transform: [{ translateX: Animated.multiply(float, 0.5) }] }}>
                <Text style={styles.introTitle} accessibilityRole="header">
                  {slide.title}
                </Text>
                <Text style={styles.introText}>{slide.text}</Text>
              </Animated.View>
            </View>
          );
        })}
      </Animated.ScrollView>

      <View style={[styles.introBottom, { paddingBottom: Math.max(insets.bottom, space.lg) + space.sm }]}>
        <View style={styles.dots} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {slides.map((slide, i) => {
            const range = [(i - 1) * width, i * width, (i + 1) * width];
            return (
              <Animated.View
                key={slide.title}
                style={[styles.dot, { width: x.interpolate({ inputRange: range, outputRange: [8, 26, 8], extrapolate: "clamp" }), opacity: x.interpolate({ inputRange: range, outputRange: [0.35, 1, 0.35], extrapolate: "clamp" }) }]}
              />
            );
          })}
        </View>
        <Button label={last ? "Get started" : "Next"} onPress={last ? onDone : () => go(index + 1)} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  barWrap: { paddingHorizontal: space.lg, paddingTop: space.sm, paddingBottom: space.xs },
  bar: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: 10, paddingHorizontal: 12 },
  barTitle: { fontFamily: fonts.bold, fontSize: 18, lineHeight: 24, letterSpacing: -0.2, color: colors.ink },
  barSub: { fontFamily: fonts.medium, fontSize: 12, lineHeight: 16, color: colors.muted },
  avatar: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "rgba(255,255,255,0.9)" },
  avatarText: { fontFamily: fonts.semibold, fontSize: 14, color: "#ffffff" },

  tabSlot: { width: 54, height: 34, alignItems: "center", justifyContent: "center" },
  pill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, borderRadius: radius.pill, backgroundColor: colors.accentSoft },
  raised: { width: 58, height: 58, borderRadius: 29, marginTop: -26, borderWidth: 3, borderColor: "rgba(255,255,255,0.95)" },
  raisedFace: { flex: 1, borderRadius: 29, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  raisedGloss: { position: "absolute", top: 0, left: 0, right: 0, height: "52%" },

  introRoot: { flex: 1, backgroundColor: colors.background },
  blob: { position: "absolute", borderRadius: 999 },
  introTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.xl, paddingBottom: space.sm },
  introBrand: { flexDirection: "row", alignItems: "center", gap: space.sm },
  introName: { fontFamily: fonts.bold, fontSize: 18, color: colors.ink, letterSpacing: -0.2 },
  skip: { fontFamily: fonts.semibold, fontSize: 15, color: colors.muted, paddingVertical: 6, paddingHorizontal: 4 },
  slide: { flex: 1, paddingHorizontal: space.xl, justifyContent: "center", gap: space.xxl },
  orbWrap: { alignItems: "center", justifyContent: "center", height: 250 },
  orb: { width: 210, height: 210, borderRadius: 105 },
  orbInner: { width: 210, height: 210, alignItems: "center", justifyContent: "center" },
  orbCore: { width: 150, height: 150, borderRadius: 75, alignItems: "center", justifyContent: "center", overflow: "hidden", ...shadow.glow },
  chip: { position: "absolute", width: 48, height: 48, borderRadius: 24, backgroundColor: "rgba(255,255,255,0.95)", alignItems: "center", justifyContent: "center", ...shadow.float },
  introTitle: { fontFamily: fonts.bold, fontSize: 28, lineHeight: 36, letterSpacing: -0.5, color: colors.ink, textAlign: "center" },
  introText: { fontFamily: fonts.regular, fontSize: 16, lineHeight: 25, color: colors.muted, textAlign: "center", marginTop: space.md, paddingHorizontal: space.sm },
  introBottom: { paddingHorizontal: space.xl, gap: space.xl },
  dots: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 6, height: 10 },
  dot: { height: 8, borderRadius: 4, backgroundColor: colors.accent },
});
