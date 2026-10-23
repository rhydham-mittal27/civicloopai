import { useEffect, useRef } from "react";
import { Animated, Easing } from "react-native";
import { colors } from "./theme";

/** The app's own loading ring, in place of the system spinner. A faint full ring with a bright arc that turns. */
export function Spinner({ size = 22, color = colors.accent }: { size?: number; color?: string }) {
  const turn = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.timing(turn, { toValue: 1, duration: 850, easing: Easing.linear, useNativeDriver: true }));
    loop.start();
    return () => loop.stop();
  }, [turn]);
  const rotate = turn.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  return (
    <Animated.View
      accessibilityRole="progressbar"
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        borderWidth: Math.max(2, size / 8),
        borderColor: `${color}33`,
        borderTopColor: color,
        transform: [{ rotate }],
      }}
    />
  );
}
