import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";
import * as Location from "expo-location";
import * as TaskManager from "expo-task-manager";
import { ApiError, createApi, type Api, type Fix } from "@civicloop/core";
import { loadServer, loadToken } from "@civicloop/ui";

/**
 * Sharing the crew's vehicle position.
 *
 * With background permission (a development or store build) the phone keeps sending with the screen off, using an
 * Android foreground service or the iOS background location mode. Expo Go cannot do that, so the screen falls back
 * to sending only while it stays open. Both paths use `deliver`, so a fix is queued and retried the same way.
 */
export const TASK = "civicloop-crew-location";
const VEHICLE_KEY = "civicloop.crew.vehicle";
const QUEUE_KEY = "civicloop.crew.queue";
const STATE_KEY = "civicloop.crew.state";
const MAX_QUEUE = 200; // about 15 minutes at one fix every 5 seconds

export interface ShareState {
  at: number | null;
  accuracy: number | null;
  queued: number;
  error: string | null;
}

export async function readState(): Promise<ShareState> {
  try {
    const raw = await AsyncStorage.getItem(STATE_KEY);
    if (raw) return JSON.parse(raw) as ShareState;
  } catch {
    /* fall through */
  }
  return { at: null, accuracy: null, queued: 0, error: null };
}

async function writeState(state: ShareState) {
  await AsyncStorage.setItem(STATE_KEY, JSON.stringify(state)).catch(() => {});
}

async function readQueue(): Promise<Fix[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as Fix[]) : [];
  } catch {
    return [];
  }
}

export function toFix(location: Location.LocationObject): Fix {
  const { latitude, longitude, speed, heading, accuracy } = location.coords;
  return {
    lat: latitude,
    lon: longitude,
    speed_kmh: speed !== null && Number.isFinite(speed) && speed >= 0 ? speed * 3.6 : undefined,
    heading: heading !== null && Number.isFinite(heading) && heading >= 0 ? heading : undefined,
    accuracy_m: accuracy !== null && Number.isFinite(accuracy) ? accuracy : undefined,
    recorded_at: new Date(location.timestamp).toISOString(),
  };
}

/**
 * Sends the new fixes, plus any that could not be sent earlier, oldest first.
 * - A network problem keeps the rest for next time.
 * - A sign-in the server no longer accepts keeps them too, and says so, so nothing is lost while the person signs in again.
 * - Any other refusal (for example the vehicle was switched off) drops that fix and is shown to the crew.
 * With the screen open the app passes its own signed-in client; the background task builds one from secure storage.
 */
export async function deliver(locations: Location.LocationObject[], signedIn?: Api): Promise<void> {
  const vehicleId = await AsyncStorage.getItem(VEHICLE_KEY);
  if (!vehicleId) return;
  const server = (await loadServer()) ?? process.env.EXPO_PUBLIC_API_URL ?? "";
  const api = signedIn ?? createApi({ baseUrl: () => server, getToken: () => loadToken(), timeoutMs: 10_000 });

  const queue = [...(await readQueue()), ...locations.map(toFix)].slice(-MAX_QUEUE);
  const keep: Fix[] = [];
  let error: string | null = null;
  let sent = 0;
  for (let i = 0; i < queue.length; i++) {
    try {
      await api.sharePosition(vehicleId, queue[i]!);
      sent++;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        error = "You have been signed out. Open the app and sign in to carry on sharing.";
        keep.push(...queue.slice(i));
        break;
      }
      if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429) {
        error = e.message; // the server will not accept this; do not keep retrying it
        continue;
      }
      error = e instanceof Error ? e.message : "Could not send";
      keep.push(...queue.slice(i));
      break;
    }
  }
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(keep)).catch(() => {});
  const last = locations[locations.length - 1];
  const before = await readState();
  await writeState({
    at: sent > 0 ? Date.now() : before.at,
    accuracy: sent > 0 ? (last?.coords.accuracy ?? before.accuracy) : before.accuracy,
    queued: keep.length,
    error,
  });
}

// Must be defined when the app's JavaScript loads, because the system starts it headless to deliver background fixes.
if (Platform.OS !== "web") {
  TaskManager.defineTask(TASK, async ({ data, error }) => {
    if (error) return;
    const locations = (data as { locations?: Location.LocationObject[] } | undefined)?.locations ?? [];
    if (locations.length) await deliver(locations);
  });
}

export type Mode = "background" | "foreground";

export async function startSharing(vehicleId: string): Promise<Mode> {
  const foreground = await Location.requestForegroundPermissionsAsync();
  if (!foreground.granted) {
    throw new Error(foreground.canAskAgain ? "Location is needed to share your vehicle's position." : "Location is turned off for this app. Turn it on in your phone's settings.");
  }
  await AsyncStorage.multiSet([
    [VEHICLE_KEY, vehicleId],
    [QUEUE_KEY, "[]"],
  ]);
  await writeState({ at: null, accuracy: null, queued: 0, error: null });

  try {
    const background = await Location.requestBackgroundPermissionsAsync();
    if (background.granted) {
      await Location.startLocationUpdatesAsync(TASK, {
        accuracy: Location.Accuracy.High,
        timeInterval: 5000,
        distanceInterval: 10,
        pausesUpdatesAutomatically: false,
        showsBackgroundLocationIndicator: true,
        foregroundService: {
          notificationTitle: "Sharing your vehicle's location",
          notificationBody: "Your supervisor can see where the vehicle is. Open CivicLoop Crew to stop.",
          notificationColor: "#14213d",
        },
      });
      return "background";
    }
  } catch {
    /* Expo Go, or a build without background location: share while the screen is open instead */
  }
  return "foreground";
}

export async function stopSharing(): Promise<void> {
  try {
    if (await Location.hasStartedLocationUpdatesAsync(TASK)) await Location.stopLocationUpdatesAsync(TASK);
  } catch {
    /* nothing was running */
  }
  await AsyncStorage.multiRemove([VEHICLE_KEY, QUEUE_KEY]).catch(() => {});
}

/** Which vehicle, if any, this phone is currently sharing, and how. */
export async function currentlySharing(): Promise<{ vehicleId: string; mode: Mode } | null> {
  const vehicleId = await AsyncStorage.getItem(VEHICLE_KEY).catch(() => null);
  if (!vehicleId) return null;
  const running = await Location.hasStartedLocationUpdatesAsync(TASK).catch(() => false);
  return { vehicleId, mode: running ? "background" : "foreground" };
}
