import type { ExpoConfig } from "expo/config";

// Plain http:// servers (a laptop on the same Wi-Fi) are blocked on Android release builds. Turn that on only for
// development builds:  CIVICLOOP_ALLOW_HTTP=1 npx expo run:android
const allowHttp = process.env.CIVICLOOP_ALLOW_HTTP === "1";
// Needed only for a store build on Android. Expo Go and iOS use their own map keys.
const mapsKey = process.env.GOOGLE_MAPS_ANDROID_KEY;

const config: ExpoConfig = {
  name: "CivicLoop Crew",
  slug: "civicloop-crew",
  scheme: "civicloopcrew",
  version: "0.1.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "light",
  ios: { supportsTablet: false, bundleIdentifier: "ai.civicloop.crew" },
  android: {
    package: "ai.civicloop.crew",
    adaptiveIcon: {
      backgroundColor: "#14213d",
      foregroundImage: "./assets/android-icon-foreground.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    predictiveBackGestureEnabled: false,
  },
  web: { bundler: "metro", output: "single", favicon: "./assets/favicon.png" },
  plugins: [
    "expo-router",
    "expo-secure-store",
    ["expo-image-picker", { photosPermission: "CivicLoop Crew uses your photos so you can send evidence of a cleanup.", cameraPermission: "CivicLoop Crew uses the camera for photos of waste sites and cleaned sites.", microphonePermission: false }],
    [
      "expo-location",
      {
        locationWhenInUsePermission: "CivicLoop Crew uses your location to mark waste sites and to show your supervisor where your vehicle is.",
        locationAlwaysAndWhenInUsePermission: "CivicLoop Crew shares your vehicle location with your supervisor while you work, even when the screen is off.",
        isIosBackgroundLocationEnabled: true,
        isAndroidBackgroundLocationEnabled: true,
        isAndroidForegroundServiceEnabled: true,
      },
    ],
    ...(mapsKey ? ([["react-native-maps", { androidGoogleMapsApiKey: mapsKey }]] as ExpoConfig["plugins"] & unknown[]) : []),
    // Release builds must not shrink the code: R8 removes a class that WorkManager (pulled in by a native library) looks up by name,
    // and the app then crashes the moment it opens. Plain http:// servers are allowed only for development builds.
    [
      "expo-build-properties",
      { android: { enableMinifyInReleaseBuilds: false, enableShrinkResourcesInReleaseBuilds: false, ...(allowHttp ? { usesCleartextTraffic: true } : {}) } },
    ],
  ],
};

export default config;
