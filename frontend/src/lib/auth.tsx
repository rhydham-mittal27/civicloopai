"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from "react";
import { getToken, setToken, type Role } from "./api";

export interface Principal {
  userId: string;
  role: Role;
  expiresAt: number;
}

interface AuthState {
  principal: Principal | null;
  ready: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function decode(token: string | null): Principal | null {
  if (!token) return null;
  try {
    const payload = token.split(".")[0].replace(/-/g, "+").replace(/_/g, "/");
    const json = JSON.parse(atob(payload + "=".repeat((4 - (payload.length % 4)) % 4)));
    if (typeof json.exp !== "number" || json.exp * 1000 <= Date.now()) return null;
    return { userId: String(json.sub), role: json.role as Role, expiresAt: json.exp * 1000 };
  } catch {
    return null;
  }
}

/* The token lives in localStorage; this tiny store lets React subscribe to it without effects. */
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
};
const emit = () => listeners.forEach((listener) => listener());
const noopSubscribe = () => () => {};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const token = useSyncExternalStore(subscribe, getToken, () => null);
  const ready = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const principal = useMemo(() => decode(token), [token]);

  const signIn = useCallback((next: string) => {
    setToken(next);
    emit();
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    emit();
  }, []);

  const value = useMemo(() => ({ principal, ready, signIn, signOut }), [principal, ready, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export const isStaff = (role: Role | undefined) =>
  role === "supervisor" || role === "admin" || role === "sanitation_worker";
export const isSupervisor = (role: Role | undefined) => role === "supervisor" || role === "admin";
