import { apiUrl } from "@/lib/api-base";

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  roles: string[];
};

class AuthClient {
  private accessToken: string | null = null;
  private roles: string[] = [];
  private refreshPromise: Promise<boolean> | null = null;
  private lastAuthError: string | null = null;

  getAccessToken(): string | null {
    return this.accessToken;
  }

  getToken(): string | null {
    return this.getAccessToken();
  }

  isAuthenticated(): boolean {
    return !!this.accessToken;
  }

  getRoles(): string[] {
    return this.roles;
  }

  getLastAuthError(): string | null {
    return this.lastAuthError;
  }

  getSubject(): string | null {
    if (!this.accessToken) return null;
    try {
      const parts = this.accessToken.split(".");
      if (parts.length < 2) return null;
      const payloadJson = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
      const payload = JSON.parse(payloadJson) as { sub?: string; user_id?: string };
      return payload.sub || payload.user_id || null;
    } catch {
      return null;
    }
  }

  async login(email: string, password: string): Promise<void> {
    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);

    const res = await fetch(apiUrl("/token"), {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
      credentials: "include", // required to receive/store the httpOnly refresh-token cookie
    });
    if (!res.ok) {
      this.lastAuthError = `login_failed:${res.status}`;
      throw new Error("Invalid credentials");
    }
    const data = (await res.json()) as TokenResponse;
    this.applyTokenResponse(data);
    this.lastAuthError = null;
  }

  async refresh(signal?: AbortSignal): Promise<boolean> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = this.refreshInternal(signal);
    try {
      return await this.refreshPromise;
    } finally {
      this.refreshPromise = null;
    }
  }

  private async refreshInternal(signal?: AbortSignal): Promise<boolean> {
    // The refresh token lives in an httpOnly cookie now — the browser sends it
    // automatically (credentials: "include"), and JS can't read it to pre-check
    // presence, so we always attempt the call and let the server say no.
    try {
      const res = await fetch(apiUrl("/refresh"), {
        method: "POST",
        credentials: "include",
        signal,
      });
      if (!res.ok) {
        let detail = `${res.status}`;
        try {
          const payload = (await res.json()) as { detail?: string; error?: string };
          detail = payload?.detail || payload?.error || detail;
        } catch {
          // Ignore parse errors; keep status-only detail
        }
        this.lastAuthError = `refresh_failed:${detail}`;
        this.clear();
        return false;
      }
      const data = (await res.json()) as TokenResponse;
      this.applyTokenResponse(data);
      this.lastAuthError = null;
      return true;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // Request was intentionally cancelled (e.g. StrictMode cleanup). Not an error.
        return false;
      }
      throw err;
    }
  }

  async logout(): Promise<void> {
    try {
      await fetch(apiUrl("/logout"), {
        method: "POST",
        credentials: "include", // sends the refresh cookie so the server can revoke it and clear it
      });
    } catch {
      // Ignore network failures during local logout.
    }
    this.clear();
  }

  private applyTokenResponse(data: TokenResponse): void {
    this.accessToken = data.access_token;
    this.roles = Array.isArray(data.roles) ? data.roles : [];
    this.lastAuthError = null;
  }

  clear(): void {
    this.accessToken = null;
    this.roles = [];
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("auth:expired"));
    }
  }
}

export const authClient = new AuthClient();
