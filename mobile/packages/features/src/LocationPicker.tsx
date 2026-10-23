import { useEffect, useRef } from "react";
import { StyleSheet, View } from "react-native";
import MapView, { Marker } from "react-native-maps";
import { colors, radius } from "@civicloop/ui";
import { DEFAULT_CENTRE } from "./place";

export interface Pin {
  lat: number;
  lon: number;
}

/** A map to drop or drag a pin on. Tap anywhere to move it. */
export function LocationPicker({ value, onChange, height = 240, interactive = true }: { value: Pin | null; onChange?: (pin: Pin) => void; height?: number; interactive?: boolean }) {
  const map = useRef<MapView>(null);
  const centre = value ?? DEFAULT_CENTRE;

  // follow the pin when it is set from outside, for example by "use my location"
  useEffect(() => {
    if (value) map.current?.animateToRegion({ latitude: value.lat, longitude: value.lon, latitudeDelta: 0.006, longitudeDelta: 0.006 }, 350);
  }, [value?.lat, value?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <View style={[styles.frame, { height }]}>
      <MapView
        ref={map}
        style={StyleSheet.absoluteFill}
        initialRegion={{ latitude: centre.lat, longitude: centre.lon, latitudeDelta: value ? 0.006 : 0.12, longitudeDelta: value ? 0.006 : 0.12 }}
        scrollEnabled={interactive}
        zoomEnabled={interactive}
        rotateEnabled={false}
        pitchEnabled={false}
        toolbarEnabled={false}
        onPress={interactive && onChange ? (e) => onChange({ lat: e.nativeEvent.coordinate.latitude, lon: e.nativeEvent.coordinate.longitude }) : undefined}
        accessibilityLabel={value ? "Map with the pin where the waste is" : "Map. Tap to place a pin where the waste is."}
      >
        {value ? (
          <Marker
            coordinate={{ latitude: value.lat, longitude: value.lon }}
            pinColor={colors.accent}
            draggable={interactive && !!onChange}
            onDragEnd={(e) => onChange?.({ lat: e.nativeEvent.coordinate.latitude, lon: e.nativeEvent.coordinate.longitude })}
          />
        ) : null}
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.sunken, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.line },
});
