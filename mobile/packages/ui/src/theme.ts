import type { Tone } from "@civicloop/core";

/**
 * The look: a soft colour backdrop with frosted-glass surfaces on top, one shiny orange accent,
 * deep navy ink, generous rounding, and Poppins for type.
 */
export const colors = {
  ink: "#0f1b3d",
  text: "#1a2547",
  muted: "#5a6483",
  faint: "#8d96b0",
  line: "rgba(15, 27, 61, 0.08)",
  background: "#eef1fb",
  surface: "#ffffff",
  sunken: "rgba(15, 27, 61, 0.05)",
  accent: "#ec5f1f",
  accentDark: "#b53d0b",
  accentSoft: "rgba(255, 138, 76, 0.18)",
  good: "#0f7a60",
  goodSoft: "rgba(24, 160, 125, 0.16)",
  warn: "#9a5200",
  warnSoft: "rgba(255, 176, 32, 0.22)",
  bad: "#c0322a",
  badSoft: "rgba(225, 70, 60, 0.15)",
  info: "#2459b8",
  infoSoft: "rgba(60, 110, 230, 0.15)",
  overlay: "rgba(15, 27, 61, 0.5)",
} as const;

/** Colour stops for gradients. Light at the top, deeper at the bottom, so surfaces look lit from above and shiny. */
export const gradients = {
  /** The shiny orange used on primary buttons and active controls. */
  accent: ["#ffa468", "#f26a25", "#c84a10"] as const,
  accentSoft: ["rgba(255,164,104,0.34)", "rgba(242,106,37,0.14)"] as const,
  /** The page behind the glass. */
  backdrop: ["#e6ecff", "#fff1e6", "#e4f3ff"] as const,
  /** A bright edge across the top of a glass surface. */
  sheen: ["rgba(255,255,255,0.7)", "rgba(255,255,255,0)"] as const,
  /** The shine across the top half of a coloured button. */
  gloss: ["rgba(255,255,255,0.42)", "rgba(255,255,255,0)"] as const,
} as const;

export const glass = {
  fill: "rgba(255, 255, 255, 0.44)",
  fillStrong: "rgba(255, 255, 255, 0.68)",
  border: "rgba(255, 255, 255, 0.92)",
  blur: 55,
} as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 14, md: 20, lg: 28, xl: 34, pill: 999 } as const;

/** Poppins. Each weight is its own font file, so the family is set per style, not with fontWeight. */
export const fonts = {
  regular: "Poppins_400Regular",
  medium: "Poppins_500Medium",
  semibold: "Poppins_600SemiBold",
  bold: "Poppins_700Bold",
} as const;

export const font = {
  title: { fontFamily: fonts.bold, fontSize: 28, lineHeight: 36, letterSpacing: -0.5 },
  heading: { fontFamily: fonts.semibold, fontSize: 18, lineHeight: 26, letterSpacing: -0.2 },
  body: { fontFamily: fonts.regular, fontSize: 15, lineHeight: 23 },
  strong: { fontFamily: fonts.semibold, fontSize: 15, lineHeight: 22 },
  small: { fontFamily: fonts.regular, fontSize: 13, lineHeight: 19 },
  label: { fontFamily: fonts.semibold, fontSize: 13, lineHeight: 18 },
};

/** Soft shadows tinted navy, never grey, so they sit naturally on the coloured backdrop. */
export const shadow = {
  card: {
    shadowColor: "#1a2a66",
    shadowOpacity: 0.14,
    shadowRadius: 26,
    shadowOffset: { width: 0, height: 12 },
    elevation: 6,
  },
  float: {
    shadowColor: "#1a2a66",
    shadowOpacity: 0.22,
    shadowRadius: 30,
    shadowOffset: { width: 0, height: 16 },
    elevation: 12,
  },
  glow: {
    shadowColor: "#ec5f1f",
    shadowOpacity: 0.42,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 8,
  },
} as const;

export const tones: Record<Tone, { bg: string; fg: string }> = {
  neutral: { bg: "rgba(15, 27, 61, 0.07)", fg: colors.muted },
  info: { bg: colors.infoSoft, fg: colors.info },
  warn: { bg: colors.warnSoft, fg: colors.warn },
  good: { bg: colors.goodSoft, fg: colors.good },
  bad: { bg: colors.badSoft, fg: colors.bad },
};

/** Thumb-friendly: every tappable thing is at least this tall. */
export const TAP = 52;

/** Space a screen leaves at the bottom so content clears the floating tab bar. */
export const TAB_CLEARANCE = 118;
