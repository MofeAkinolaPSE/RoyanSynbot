import { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { canViewByRoles, resolveRouteRoles } from "@/lib/nav-access";

const ProtectedRoute = ({ children }: PropsWithChildren) => {
  const { isAuthenticated, isLoading, roles } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="pw-page-surface min-h-screen flex items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Access rules are derived from nav-items.ts (the sidebar's own source of
  // truth) rather than a second hand-maintained list — the two used to be
  // separate and had already drifted (a receptionist could see "Front Desk"
  // in the sidebar but get bounced out on click; a management user could see
  // "Compliance" but not open it). Deriving both from one place makes that
  // class of bug structurally impossible.
  const requiredRoles = resolveRouteRoles(location.pathname);
  if (requiredRoles && !canViewByRoles(roles, requiredRoles)) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
