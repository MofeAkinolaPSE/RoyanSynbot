import { PropsWithChildren, createContext, useContext, useEffect, useMemo, useState } from "react";
import { authClient } from "@/lib/auth-client";
import { usePresenceHeartbeat } from "@/hooks/use-presence-heartbeat";

type AuthContextValue = {
  isAuthenticated: boolean;
  isLoading: boolean;
  roles: string[];
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<boolean>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
};

const AuthProvider = ({ children }: PropsWithChildren) => {
  // Optimistic auth: if an access token is already in memory (e.g. navigated here
  // right after login), trust it immediately. Otherwise we can't know client-side
  // whether a session exists — the refresh token lives in an httpOnly cookie that
  // JS can't read — so show a brief loading state and always attempt a background
  // refresh() to find out; the server will say no quickly if there's no cookie.
  const [isLoading, setIsLoading] = useState(!authClient.isAuthenticated());
  const [isAuthenticated, setIsAuthenticated] = useState(authClient.isAuthenticated());
  const [roles, setRoles] = useState<string[]>(authClient.getRoles());

  usePresenceHeartbeat(isAuthenticated);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const onAuthExpired = () => {
      if (!active) return;
      setIsAuthenticated(false);
      setRoles([]);
    };
    window.addEventListener("auth:expired", onAuthExpired as EventListener);

    if (authClient.isAuthenticated()) {
      // Access token already in memory (e.g. navigated here right after login) — nothing to do.
      setIsLoading(false);
    } else {
      // Cold page load — attempt to restore the session via the httpOnly refresh cookie.
      (async () => {
        const ok = await authClient.refresh(controller.signal);
        if (!active) return;
        const roleList = authClient.getRoles();
        setIsAuthenticated(ok || authClient.isAuthenticated());
        setRoles(roleList);
        if (ok) {
          localStorage.setItem("synbot_config", JSON.stringify({
            apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "",
            role: roleList[0] ?? "staff",
          }));
        }
        setIsLoading(false);
      })();
    }

    return () => {
      active = false;
      controller.abort();
      window.removeEventListener("auth:expired", onAuthExpired as EventListener);
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      isLoading,
      login: async (email: string, password: string) => {
        await authClient.login(email, password);
        setIsAuthenticated(true);
        const roleList = authClient.getRoles();
        setRoles(roleList);
        localStorage.setItem("synbot_config", JSON.stringify({
          apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "",
          role: roleList[0] ?? "staff",
        }));
      },
      logout: async () => {
        await authClient.logout();
        localStorage.removeItem("synbot_config");
        setIsAuthenticated(false);
        setRoles([]);
      },
      refresh: async () => {
        const ok = await authClient.refresh();
        const roleList = authClient.getRoles();
        setIsAuthenticated(ok || authClient.isAuthenticated());
        setRoles(roleList);
        if (ok) {
          localStorage.setItem("synbot_config", JSON.stringify({
            apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "",
            role: roleList[0] ?? "staff",
          }));
        }
        return ok;
      },
      roles,
    }),
    [isAuthenticated, isLoading, roles],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export default AuthProvider;
