import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import type { AppConfig, User } from "./types";

interface Ctx {
  config: AppConfig | null;
  user: User | null;
  loading: boolean;
  setUser: (u: User | null) => void;
  ensureUser: () => Promise<User>;
  refreshUser: () => Promise<void>;
  toast: (msg: string) => void;
  theme: string;
  setTheme: (t: string) => void;
}

const AppCtx = createContext<Ctx | null>(null);
const THEME_KEY = "theme-override";

function readThemeOverride(): string | null {
  try { return localStorage.getItem(THEME_KEY); } catch { return null; }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [theme, setThemeState] = useState<string>(readThemeOverride() ?? "yellow-black");

  useEffect(() => {
    api.config().then((c) => {
      setConfig(c);
      if (!readThemeOverride()) setThemeState(c.theme);
      document.title = `${c.brand.name} · ${c.brand.tagline}`;
    }).catch(() => undefined);
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  const setTheme = useCallback((t: string) => {
    setThemeState(t);
    try { localStorage.setItem(THEME_KEY, t); } catch { /* private mode */ }
  }, []);

  const ensureUser = useCallback(async () => {
    if (user) return user;
    try {
      const u = await api.me();
      setUser(u);
      return u;
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) throw e;
    }
    const g = await api.guest();
    setUser(g);
    return g;
  }, [user]);

  const refreshUser = useCallback(async () => {
    try { setUser(await api.me()); } catch { setUser(null); }
  }, []);

  const toast = useCallback((m: string) => {
    setMsg(m);
    window.setTimeout(() => setMsg((cur) => (cur === m ? null : cur)), 3200);
  }, []);

  const value = useMemo(() => ({ config, user, loading, setUser, ensureUser, refreshUser, toast, theme, setTheme }),
    [config, user, loading, ensureUser, refreshUser, toast, theme, setTheme]);

  return (
    <AppCtx.Provider value={value}>
      {children}
      {msg && <div className="toast" role="status">{msg}</div>}
    </AppCtx.Provider>
  );
}

export function useApp(): Ctx {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside AppProvider");
  return c;
}

export function brandName(config: AppConfig | null) {
  return config?.brand.name ?? "Thruwear";
}
