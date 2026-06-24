import { PropsWithChildren, createContext, useContext, useEffect, useMemo, useState } from "react";
import { authClient } from "@/lib/auth-client";

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

const STORED_REFRESH_KEY = "refresh_token";

const AuthProvider = ({ children }: PropsWithChildren) => {
  // Optimistic auth: if a refresh token is already stored (or an access token is in
  // memory), trust it immediately and verify in the background instead of blocking
  // the entire render tree on a network round-trip to /refresh.
  const hasStoredSession =
    authClient.isAuthenticated() || !!localStorage.getItem(STORED_REFRESH_KEY);

  const [isLoading, setIsLoading] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(hasStoredSession);
  const [roles, setRoles] = useState<string[]>(authClient.getRoles());

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
    } else if (!localStorage.getItem(STORED_REFRESH_KEY)) {
      // No tokens at all — mark unauthenticated immediately.
      setIsAuthenticated(false);
      setIsLoading(false);
    } else {
      // Have a stored refresh token but no access token (cold page load).
      // Signal loading so consumers (Sidebar) don't filter on stale empty roles.
      setIsLoading(true);
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
