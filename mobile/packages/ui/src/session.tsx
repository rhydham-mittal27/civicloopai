import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, createApi, normaliseServerUrl, type Api, type Me, type Role } from "@civicloop/core";
import { loadServer, loadToken, saveServer, saveToken } from "./storage";

type Status = "loading" | "signedOut" | "signedIn";

interface SessionValue {
  api: Api;
  me: Me | null;
  status: Status;
  serverUrl: string;
  setServerUrl: (url: string) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  /** For the resident app: keep the token a new account just earned, without a second sign-in screen. */
  signInWithToken: (token: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

interface Props {
  /** The one role this app is for. Anyone else is turned away with a clear message. */
  expectedRole: Role;
  roleName: string;
  defaultServer?: string;
  children: ReactNode;
}

export function SessionProvider({ expectedRole, roleName, defaultServer = "", children }: Props) {
  const token = useRef<string | null>(null);
  const server = useRef<string>(normaliseServerUrl(defaultServer));
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [serverUrl, setServerUrlState] = useState(server.current);

  const clear = useCallback(async () => {
    token.current = null;
    await saveToken(null);
    setMe(null);
    setStatus("signedOut");
  }, []);

  const api = useMemo(
    () =>
      createApi({
        baseUrl: () => server.current,
        getToken: () => token.current,
        onUnauthorized: () => {
          void clear();
        },
      }),
    [clear],
  );

  const load = useCallback(
    async (fresh: string) => {
      token.current = fresh;
      await saveToken(fresh);
      const who = await api.me();
      if (who.role !== expectedRole) {
        await clear();
        throw new Error(`This app is for ${roleName}. Please use the website for your role.`);
      }
      setMe(who);
      setStatus("signedIn");
    },
    [api, clear, expectedRole, roleName],
  );

  // pick up the saved server address and sign-in when the app opens
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [savedServer, savedToken] = await Promise.all([loadServer(), loadToken()]);
      if (cancelled) return;
      if (savedServer) {
        server.current = savedServer;
        setServerUrlState(savedServer);
      } else if (server.current) {
        // a default built into the app is saved too, so the background location task (which has no screen) can read it
        await saveServer(server.current);
      }
      if (!savedToken) {
        setStatus("signedOut");
        return;
      }
      token.current = savedToken;
      try {
        const who = await api.me();
        if (cancelled) return;
        if (who.role !== expectedRole) await clear();
        else {
          setMe(who);
          setStatus("signedIn");
        }
      } catch (error) {
        if (cancelled) return;
        // a rejected token already signed out; with no network we stay signed in and try again later
        if (!(error instanceof ApiError && error.status === 401)) setStatus("signedIn");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, clear, expectedRole]);

  const value = useMemo<SessionValue>(
    () => ({
      api,
      me,
      status,
      serverUrl,
      setServerUrl: async (url) => {
        const clean = normaliseServerUrl(url);
        server.current = clean;
        setServerUrlState(clean);
        await saveServer(clean);
      },
      signIn: async (email, password) => {
        const { access_token } = await api.login(email.trim(), password);
        await load(access_token);
      },
      signInWithToken: load,
      signOut: clear,
      refreshMe: async () => {
        try {
          setMe(await api.me());
        } catch {
          /* keep what we have */
        }
      },
    }),
    [api, clear, load, me, serverUrl, status],
  );

  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside a SessionProvider");
  return value;
}
