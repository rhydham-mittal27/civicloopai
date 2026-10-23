import { useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import { colors, radius } from "@civicloop/ui";
import { DEFAULT_CENTRE } from "./place";

export interface Pin {
  lat: number;
  lon: number;
}

const TILE = 256;

/** Web Mercator, the same maths every slippy map uses. */
function toWorld(lat: number, lon: number, zoom: number) {
  const scale = TILE * 2 ** zoom;
  const sin = Math.sin((lat * Math.PI) / 180);
  return { x: ((lon + 180) / 360) * scale, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale };
}

function fromWorld(x: number, y: number, zoom: number): Pin {
  const scale = TILE * 2 ** zoom;
  const lon = (x / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * y) / scale;
  return { lat: (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))), lon };
}

/**
 * Browser version of the map picker (the native one uses the phone's map). Real OpenStreetMap tiles, a pin, and tap to move it.
 * It exists so the app can be previewed and tested in a browser; phones use LocationPicker.tsx.
 */
export function LocationPicker({ value, onChange, height = 240, interactive = true }: { value: Pin | null; onChange?: (pin: Pin) => void; height?: number; interactive?: boolean }) {
  const [width, setWidth] = useState(340);
  const zoom = value ? 16 : 13;
  const centre = value ?? DEFAULT_CENTRE;
  const c = toWorld(centre.lat, centre.lon, zoom);
  const first = { x: Math.floor((c.x - width / 2) / TILE), y: Math.floor((c.y - height / 2) / TILE) };
  const tiles: { key: string; x: number; y: number; src: string }[] = [];
  for (let tx = first.x; tx * TILE < c.x + width / 2; tx++) {
    for (let ty = first.y; ty * TILE < c.y + height / 2; ty++) {
      tiles.push({ key: `${tx}/${ty}`, x: tx * TILE - c.x + width / 2, y: ty * TILE - c.y + height / 2, src: `https://tile.openstreetmap.org/${zoom}/${tx}/${ty}.png` });
    }
  }

  return (
    <View style={[styles.frame, { height }]} onLayout={(e) => setWidth(e.nativeEvent.layout.width)} accessibilityLabel={value ? "Map with the pin where the waste is" : "Map. Tap to place a pin where the waste is."}>
      {tiles.map((t) => (
        <Image key={t.key} source={{ uri: t.src }} style={{ position: "absolute", left: t.x, top: t.y, width: TILE, height: TILE }} />
      ))}
      <Pressable
        style={StyleSheet.absoluteFill}
        disabled={!interactive || !onChange}
        onPress={(e) => {
          const { locationX, locationY } = e.nativeEvent;
          onChange?.(fromWorld(c.x - width / 2 + locationX, c.y - height / 2 + locationY, zoom));
        }}
      />
      {value ? (
        <View pointerEvents="none" style={[styles.pin, { left: width / 2 - 14, top: height / 2 - 34 }]}>
          <View style={styles.pinHead} />
          <View style={styles.pinTip} />
        </View>
      ) : null}
      <Text style={styles.credit}>© OpenStreetMap contributors</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.sunken, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.line },
  pin: { position: "absolute", width: 28, height: 36, alignItems: "center" },
  pinHead: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.accent, borderWidth: 3, borderColor: "#ffffff" },
  pinTip: { width: 0, height: 0, borderLeftWidth: 6, borderRightWidth: 6, borderTopWidth: 10, borderLeftColor: "transparent", borderRightColor: "transparent", borderTopColor: colors.accent, marginTop: -3 },
  credit: { position: "absolute", right: 6, bottom: 4, fontSize: 10, color: colors.ink, backgroundColor: "rgba(255,255,255,0.8)", paddingHorizontal: 4, borderRadius: 4 },
});
