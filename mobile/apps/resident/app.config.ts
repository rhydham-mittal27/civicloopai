import type { ExpoConfig } from "expo/config";

// Plain http:// servers (a laptop on the same Wi-Fi) are blocked on Android release builds. Turn that on only for
// development builds:  CIVICLOOP_ALLOW_HTTP=1 npx expo run:android
const allowHttp = process.env.CIVICLOOP_ALLOW_HTTP === "1";
// Needed only for a store build on Android. Expo Go and iOS use their own map keys.
const mapsKey = process.env.GOOGLE_MAPS_ANDROID_KEY;

const config: ExpoConfig = {
  name: "CivicLoop",
  slug: "civicloop-resident",
  scheme: "civicloop",
  version: "0.1.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "light",
  ios: { supportsTablet: false, bundleIdentifier: "ai.civicloop.resident" },
  android: {
    package: "ai.civicloop.resident",
    adaptiveIcon: {
      backgroundColor: "#d4501a",
      foregroundImage: "./assets/android-icon-foreground.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    predictiveBackGestureEnabled: false,
  },
  web: { bundler: "metro", output: "single", favicon: "./assets/favicon.png" },
  plugins: [
    "expo-router",
    "expo-secure-store",
    ["expo-image-picker", { photosPermission: "CivicLoop uses your photos so you can add pictures to a report.", cameraPermission: "CivicLoop uses the camera so you can photograph the waste.", microphonePermission: false }],
    ["expo-location", { locationWhenInUsePermission: "CivicLoop uses your location to mark where the waste is." }],
    ...(mapsKey ? ([["react-native-maps", { androidGoogleMapsApiKey: mapsKey }]] as ExpoConfig["plugins"] & unknown[]) : []),
    ...(allowHttp ? ([["expo-build-properties", { android: { usesCleartextTraffic: true } }]] as ExpoConfig["plugins"] & unknown[]) : []),
  ],
};

export default config;
