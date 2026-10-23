import * as ImagePicker from "expo-image-picker";
import type { UploadFile } from "@civicloop/core";
import type { DialogApi } from "@civicloop/ui";

function toUpload(asset: ImagePicker.ImagePickerAsset): UploadFile {
  const name = asset.fileName ?? `photo-${Date.now()}.jpg`;
  const type = asset.mimeType ?? (name.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg");
  return { uri: asset.uri, name, type };
}

/**
 * Opens the camera. Before the phone asks for permission, the app explains why in its own dialog, and if the camera was
 * turned off for good it offers to open the settings. Returns null if the person declines or backs out.
 */
export async function takePhoto(dialog: DialogApi): Promise<UploadFile | null> {
  let permission = await ImagePicker.getCameraPermissionsAsync();
  if (!permission.granted) {
    if (permission.canAskAgain) {
      const go = await dialog.explain({ title: "Allow the camera?", message: "CivicLoop uses the camera to photograph waste sites and cleaned sites. Your phone will ask you to confirm next.", icon: "camera" });
      if (!go) return null;
      permission = await ImagePicker.requestCameraPermissionsAsync();
    }
    if (!permission.granted) {
      await dialog.openSettingsFor({ title: "The camera is turned off", message: "To take photos, allow the camera for CivicLoop in your phone's settings. You can still pick photos from the gallery.", icon: "camera" });
      return null;
    }
  }
  const result = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.7 });
  const first = result.canceled ? null : result.assets[0];
  return first ? toUpload(first) : null;
}

/** Lets the person pick up to `limit` photos from the gallery. Photos are shrunk a little so uploads stay quick on mobile data. */
export async function choosePhotos(limit: number): Promise<UploadFile[]> {
  if (limit <= 0) return [];
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ["images"],
    allowsMultipleSelection: limit > 1,
    selectionLimit: limit,
    quality: 0.7,
  });
  return result.canceled ? [] : result.assets.slice(0, limit).map(toUpload);
}
