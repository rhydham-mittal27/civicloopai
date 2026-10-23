import { useCallback, useEffect, useRef, useState } from "react";

interface Loaded<T> {
  data?: T;
  error?: string;
}

/**
 * Loads something when the screen opens and whenever `deps` change. Keeps the old data on screen while it
 * refreshes, so a pull-to-refresh never flashes empty.
 */
export function useLoad<T>(load: () => Promise<T>, deps: readonly unknown[] = []) {
  const [state, setState] = useState<Loaded<T>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const latest = useRef(load);
  latest.current = load;
  const run = useRef(0);

  const fetchNow = useCallback(async (isRefresh: boolean) => {
    const mine = ++run.current;
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await latest.current();
      if (mine === run.current) setState({ data });
    } catch (error) {
      if (mine === run.current) setState((s) => ({ data: s.data, error: error instanceof Error ? error.message : "Something went wrong" }));
    } finally {
      if (mine === run.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void fetchNow(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return {
    data: state.data,
    error: state.error,
    loading,
    refreshing,
    reload: () => fetchNow(false),
    refresh: () => fetchNow(true),
  };
}

/** Runs one action at a time and remembers its error, for buttons that call the server. */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>): Promise<T | undefined> => {
    setError(null);
    setBusy(key);
    try {
      return await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      return undefined;
    } finally {
      setBusy(null);
    }
  }, []);

  return { busy, error, run, clear: () => setError(null) };
}
