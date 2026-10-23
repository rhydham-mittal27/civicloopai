import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

/**
 * The sign-in token and server address live in the phone's secure storage. They are plain functions, not React,
 * because the background location task runs without any screen on display and must read them too.
 */
const TOKEN_KEY = "civicloop.token";
const SERVER_KEY = "civicloop.server";

export async function loadToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function saveToken(token: string | null): Promise<void> {
  try {
    if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
    else await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch {
    /* the session then lives in memory only, and the next launch asks to sign in again */
  }
}

export async function loadServer(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(SERVER_KEY);
  } catch {
    return null;
  }
}

export async function saveServer(url: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(SERVER_KEY, url);
  } catch {
    /* ignore: the address stays for this run */
  }
}

/** Small yes/no facts such as "has seen the welcome screens". A browser has no secure store, so it uses localStorage. */
export async function loadFlag(name: string): Promise<boolean> {
  const key = `civicloop.flag.${name}`;
  try {
    if (Platform.OS === "web") return globalThis.localStorage?.getItem(key) === "1";
    return (await SecureStore.getItemAsync(key)) === "1";
  } catch {
    return false;
  }
}

export async function saveFlag(name: string, value: boolean): Promise<void> {
  const key = `civicloop.flag.${name}`;
  try {
    if (Platform.OS === "web") {
      if (value) globalThis.localStorage?.setItem(key, "1");
      else globalThis.localStorage?.removeItem(key);
    } else if (value) await SecureStore.setItemAsync(key, "1");
    else await SecureStore.deleteItemAsync(key);
  } catch {
    /* the welcome screens would show once more next launch */
  }
}
