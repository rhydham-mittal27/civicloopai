"use client";

import { useCallback, useEffect, useEffectEvent, useState } from "react";
import { useToast } from "@/components/Toast";

interface Loaded<T> {
  nonce: number;
  depsKey: string;
  data?: T;
  error?: string;
}

/** Fetches on mount and whenever `deps` change. Keeps the previous data while refetching. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [nonce, setNonce] = useState(0);
  const [result, setResult] = useState<Loaded<T> | null>(null);
  const depsKey = JSON.stringify(deps);
  const run = useEffectEvent(load);

  useEffect(() => {
    let cancelled = false;
    run()
      .then((data) => !cancelled && setResult({ nonce, depsKey, data }))
      .catch((err) => !cancelled && setResult({ nonce, depsKey, error: err instanceof Error ? err.message : "Something went wrong" }));
    return () => {
      cancelled = true;
    };
  }, [nonce, depsKey]);

  const loading = !result || result.nonce !== nonce || result.depsKey !== depsKey;
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return {
    data: result?.data,
    error: loading ? undefined : result?.error,
    loading,
    reload,
  };
}

/** Wraps a mutation: tracks which one is running, surfaces the error, optionally toasts. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async <T,>(key: string, fn: () => Promise<T>, success?: string): Promise<T | undefined> => {
      setError(null);
      setBusy(key);
      try {
        const value = await fn();
        if (success) toast(success);
        return value;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong");
        return undefined;
      } finally {
        setBusy(null);
      }
    },
    [toast],
  );

  return { busy, error, run, clear: () => setError(null) };
}
