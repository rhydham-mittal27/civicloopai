import { useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, radius } from "@civicloop/ui";
import { DEFAULT_CENTRE } from "./place";

export interface Pin {
  lat: number;
  lon: number;
}

const TILE = 256;
const MIN_ZOOM = 3;
const MAX_ZOOM = 19;
// OpenStreetMap asks every app to say who it is. (Browsers set their own and ignore this.)
const TILE_HEADERS = { "User-Agent": "CivicLoop/0.1 (waste reporting app; civicloop.ai)" };

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
 * A map to drop a pin on: real OpenStreetMap tiles, tap to place the pin, plus and minus to zoom.
 *
 * It is drawn with plain React Native views, the same on Android, iOS and the web. The phone's own map (Google Maps on
 * Android) needs a Google API key, and without one the app crashes the moment a map opens, so it is not used.
 */
export function LocationPicker({ value, onChange, height = 240, interactive = true }: { value: Pin | null; onChange?: (pin: Pin) => void; height?: number; interactive?: boolean }) {
  const [width, setWidth] = useState(340);
  const [zoomed, setZoomed] = useState<number | null>(null);
  const zoom = zoomed ?? (value ? 16 : 13);
  const centre = value ?? DEFAULT_CENTRE;
  const c = toWorld(centre.lat, centre.lon, zoom);
  const first = { x: Math.floor((c.x - width / 2) / TILE), y: Math.floor((c.y - height / 2) / TILE) };
  const limit = 2 ** zoom;
  const tiles: { key: string; x: number; y: number; src: string }[] = [];
  for (let tx = first.x; tx * TILE < c.x + width / 2; tx++) {
    for (let ty = first.y; ty * TILE < c.y + height / 2; ty++) {
      if (ty < 0 || ty >= limit) continue;
      const wrapped = ((tx % limit) + limit) % limit;
      tiles.push({ key: `${tx}/${ty}`, x: tx * TILE - c.x + width / 2, y: ty * TILE - c.y + height / 2, src: `https://tile.openstreetmap.org/${zoom}/${wrapped}/${ty}.png` });
    }
  }
  const zoomBy = (step: number) => setZoomed(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom + step)));

  return (
    <View style={[styles.frame, { height }]} onLayout={(e) => setWidth(e.nativeEvent.layout.width)} accessibilityLabel={value ? "Map with the pin where the waste is" : "Map. Tap to place a pin where the waste is."}>
      {tiles.map((t) => (
        <Image key={t.key} source={{ uri: t.src, headers: TILE_HEADERS }} style={{ position: "absolute", left: t.x, top: t.y, width: TILE, height: TILE }} />
      ))}
      <Pressable
        style={StyleSheet.absoluteFill}
        disabled={!interactive || !onChange}
        accessibilityRole="button"
        accessibilityLabel="Tap the map to place the pin"
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
      {interactive ? (
        <View style={styles.zoom}>
          <Pressable onPress={() => zoomBy(1)} accessibilityRole="button" accessibilityLabel="Zoom in" hitSlop={6} style={styles.zoomButton}>
            <Text style={styles.zoomText}>+</Text>
          </Pressable>
          <Pressable onPress={() => zoomBy(-1)} accessibilityRole="button" accessibilityLabel="Zoom out" hitSlop={6} style={styles.zoomButton}>
            <Text style={styles.zoomText}>−</Text>
          </Pressable>
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
  zoom: { position: "absolute", right: 10, top: 10, gap: 6 },
  zoomButton: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.94)", borderWidth: StyleSheet.hairlineWidth, borderColor: colors.line },
  zoomText: { fontFamily: fonts.semibold, fontSize: 22, lineHeight: 26, color: colors.ink },
  credit: { position: "absolute", right: 6, bottom: 4, fontSize: 10, color: colors.ink, backgroundColor: "rgba(255,255,255,0.8)", paddingHorizontal: 4, borderRadius: 4 },
});
