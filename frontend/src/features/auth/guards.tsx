import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { UserRole } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Loading } from "@/components/ui/Spinner";
import { useAuth } from "@/features/auth/authContext";
import { ForbiddenPage } from "./StatusPages";
import s from "./guards.module.css";

/** Signed-in users only. Anyone else is sent to the sign-in page and brought back afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state, retry } = useAuth();
  const location = useLocation();

  if (state.status === "loading") return <Loading label="Opening your session" />;
  if (state.status === "unreachable") {
    return (
      <div role="alert" className={s.unreachable}>
        <h1>The server cannot be reached</h1>
        <p>Check your connection, then try again.</p>
        <Button variant="primary" onClick={retry}>
          Try again
        </Button>
      </div>
    );
  }
  if (state.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

/** The sign-in page is for people who are not signed in yet. */
export function PublicOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") return <Loading label="Opening your session" />;
  if (state.status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? "/"} replace />;
  }
  return <>{children}</>;
}

/** Hides a whole page from roles that cannot use it. The API enforces this as well. */
export function RequireRole({ roles, children }: { roles: UserRole[]; children: ReactNode }) {
  const { state } = useAuth();
  if (state.status !== "authenticated") return null;
  return roles.includes(state.user.role) ? <>{children}</> : <ForbiddenPage />;
}
