import * as Location from "expo-location";
import type { DialogApi } from "@civicloop/ui";

export interface Place {
  lat: number;
  lon: number;
  accuracy: number | null;
}

/**
 * Where the phone is right now. The app explains why it needs location before the phone asks, and if location was
 * turned off for good it offers to open the settings. Returns null if the person declines.
 */
export async function currentPlace(dialog: DialogApi): Promise<Place | null> {
  let permission = await Location.getForegroundPermissionsAsync();
  if (!permission.granted) {
    if (permission.canAskAgain) {
      const go = await dialog.explain({ title: "Use your location?", message: "CivicLoop uses your location once, to put the pin where you are. Your phone will ask you to confirm next.", icon: "location" });
      if (!go) return null;
      permission = await Location.requestForegroundPermissionsAsync();
    }
    if (!permission.granted) {
      await dialog.openSettingsFor({ title: "Location is turned off", message: "To use your location, allow it for CivicLoop in your phone's settings. Or tap the map to place the pin yourself.", icon: "location" });
      return null;
    }
  }
  const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
  return { lat: position.coords.latitude, lon: position.coords.longitude, accuracy: position.coords.accuracy ?? null };
}

/** A starting view over Chandigarh, the pilot city, used when nothing else is known. */
export const DEFAULT_CENTRE = { lat: 30.7333, lon: 76.7794 };
