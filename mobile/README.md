# CivicLoopAI mobile apps

Two phone apps for the two people who work in the field, built with Expo (React Native) and TypeScript, sharing one API client.

| App | For | What it does |
| --- | --- | --- |
| **CivicLoop** (`apps/resident`) | Residents | Create an account for your city, report waste with photos and a map pin, follow each report until it is cleaned |
| **CivicLoop Crew** (`apps/crew`) | Sanitation crews | See assigned jobs, start and finish them, send the after-photo, share the vehicle's GPS, report sites found on the round |

Screenshots of every screen are in [`docs/mobile/`](../docs/mobile/README.md).

## The look

A soft colour backdrop (orange and blue glows) with frosted-glass surfaces on top: translucent cards with a blur, a bright top
edge and a thin white rim, a floating glass tab bar, and glass top bars on pushed screens. Primary actions are glossy
orange gradient pills with a soft glow. Everything is rounded (cards 28, controls fully round), the type is **Poppins**, and
shadows are tinted navy. All of it lives in `packages/ui` (`theme.ts`, `components.tsx`), so both apps change together.
On phones the blur is the system's own (`expo-blur`); on Android it uses Expo's experimental blur method.

## How it is laid out

```
mobile/
  apps/resident/        Expo app: sign in, register, my reports, report form, report detail, account
  apps/crew/            Expo app: jobs, job detail, vehicle location, report, account
  packages/core/        Typed API client, types, labels, formatting. No React Native, so it is tested in Node.
  packages/ui/          Theme, components, the signed-in session and secure token storage
  packages/features/    Screens both apps share: sign in, server address, report form, report detail, account
  scripts/              Icons, web preview server, screenshot capture
```

Routes live in `src/app/` of each app (Expo Router). Each route file is a few lines that mount a shared screen, so the two apps
cannot drift apart. Sign-in uses protected routes: signed-out people only reach sign in, signed-in people only reach the app.

Each app accepts only its own role. A supervisor who signs in to the resident app is told to use the website.

## No system popups

Every question, warning and choice in the apps is drawn by the app, in the glass style, never by the phone's alert box:

- **Dialogs** (`useDialog()` in `packages/ui/src/dialogs.tsx`): `confirm`, `alert`, `choose` (a bottom sheet) and two helpers for
  permissions. They are promises, so a screen writes `if (await dialog.confirm({...})) { ... }`. They dim and blur what is
  behind, close with the Android back button, and are announced as alerts to screen readers.
- **Permission explainers**: before the phone asks for the camera, location or background location, the app says why in its own
  dialog. If a permission was turned off for good, a dialog offers to open the phone's settings.
- **Spinner** and **pull-to-refresh**: the app's own animated ring, not the system spinner.
- **Error and not-found screens**: the app's own, replacing the router's built-in ones.

Still drawn by the phone and not replaceable from inside the app: the **system permission prompt** itself (the explainer comes first),
the **camera app** and the **gallery picker** that open when a photo is taken or chosen, and the maps app that "Navigate" and
"Open in maps" hand over to. Replacing the camera and gallery with in-app versions is possible (a custom camera screen and a
gallery grid) but has not been built.

## Run it on a phone

You need Node 22 or newer (Expo SDK 58 requires it), the backend running, and the **Expo Go** app on your phone.

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL=http://<your-computer-lan-ip>:8000 npm run resident   # or: npm run crew
```

Scan the QR code with Expo Go. Phone and computer must be on the same Wi-Fi. You can also leave `EXPO_PUBLIC_API_URL` out and type
the address on the sign-in screen ("Set server address"); the app remembers it.

Accounts: residents register in the app. Crew accounts are created by a city admin on the website (Users page) and the crew
member is assigned a vehicle on the Live fleet page.

### What needs a development build instead of Expo Go

- **Sharing location with the screen off** (the crew app). Expo Go cannot run background location. In Expo Go the app falls back
  to sharing while the screen stays open and says so on screen. For background sharing build a development or store build:
  `CIVICLOOP_ALLOW_HTTP=1 npx expo run:android` (the flag allows a plain http:// server on your Wi-Fi; use HTTPS in production).
- **Google Maps on Android store builds** need `GOOGLE_MAPS_ANDROID_KEY`. Expo Go and iOS need nothing.

## Checks

```bash
npm test                                                   # 15 unit tests for the client and helpers
CIVICLOOP_CONTRACT_URL=http://127.0.0.1:8000 npm test      # plus 5 contract tests against a running backend
npm run typecheck
```

`npx expo export --platform android` (and `ios`, `web`) must succeed for both apps, and `npx expo-doctor` must pass 20 of 20.

## What has and has not been verified

Verified: unit and contract tests, TypeScript, successful production bundles for Android, iOS and web, Expo doctor, and every
screen rendered and driven in a phone-sized browser against the real backend (sign in, create account form, server test, report
form with chips, photo and location, report detail with map and photos, account, jobs, job detail, location sharing).

**Not verified: a real phone.** No device or emulator was available. The screens above are the real app code running through
React Native Web, so these are not tested on a handset:

- native maps (the web preview draws the same pin on OpenStreetMap tiles instead of the phone's map),
- the camera, and background location with the screen off (the Android foreground service, the iOS background mode),
- iOS and Android permission prompts and the secure token storage (secure storage does not exist in a browser, so the web
  preview keeps the sign-in in memory only),
- release builds, store signing and push notifications (not built).

Please run both apps on a real Android and iPhone before relying on them.

## Preview in a browser

```bash
cd mobile/apps/resident && EXPO_PUBLIC_API_URL=http://localhost:8082 npx expo export --platform web --output-dir /tmp/resident
python mobile/scripts/preview_server.py /tmp/resident 8082      # serves the app and forwards /api to the backend
```

`mobile/scripts/screenshots.mjs` drives both previews and writes the screenshots (see the header of that file).
