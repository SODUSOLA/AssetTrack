import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, unwrap } from "@/api/client";
import { isApiError } from "@/api/errors";
import { session } from "@/api/session";

import { AuthContext, type AuthState } from "./authContext";

async function loadUser(): Promise<AuthState> {
  try {
    const user = await unwrap(api.GET("/api/v1/auth/me"));
    return { status: "authenticated", user };
  } catch (error) {
    return { status: isApiError(error) && error.isNetwork ? "unreachable" : "anonymous" };
  }
}

/**
 * Owns who is signed in. On start it quietly tries to refresh (the browser sends the httpOnly
 * cookie); success means the user is still signed in, a refusal shows the sign-in page.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await session.refresh();
      const next: AuthState = result.ok
        ? await loadUser()
        : { status: result.reason === "denied" ? "anonymous" : "unreachable" };
      if (!cancelled) setState(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(
    () =>
      session.onExpired(() => {
        queryClient.clear();
        setState({ status: "anonymous" });
      }),
    [queryClient],
  );

  const login = useCallback(async (email: string, password: string) => {
    const token = await unwrap(api.POST("/api/v1/auth/login", { body: { email, password } }));
    session.start(token.access_token, token.expires_in);
    const next = await loadUser();
    if (next.status !== "authenticated") {
      session.end();
      throw new Error("Signed in, but your profile could not be loaded.");
    }
    setState(next);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.POST("/api/v1/auth/logout");
    } catch {
      /* the local session ends regardless */
    }
    session.end();
    queryClient.clear();
    setState({ status: "anonymous" });
  }, [queryClient]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const value = useMemo(() => ({ state, login, logout, retry }), [state, login, logout, retry]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
