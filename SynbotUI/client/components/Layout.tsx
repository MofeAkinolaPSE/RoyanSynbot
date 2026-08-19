import Sidebar from "./Sidebar";
import FloatingChat from "./FloatingChat";
import ProfileSetup from "./ProfileSetup";
import { NotificationBell } from "./NotificationBell";
import { Outlet, useLocation } from "react-router-dom";
import { getSynbotConfig } from "@/lib/wp-config";
import { Button } from "@/components/ui/button";
import { BackButton } from "@/components/BackButton";
import { useState, useEffect } from "react";
import { Menu } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { api } from "@/lib/api-client";
import { useTour } from "@/components/tour/TourProvider";

const Layout = () => {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();
  const { role, apiBaseUrl, wpUserId } = getSynbotConfig();
  const { isAuthenticated, roles } = useAuth();
  const { startTourIfNeeded } = useTour();
  const [showSetup, setShowSetup] = useState(false);
  const [staffData, setStaffData] = useState<any>(null);

  useEffect(() => {
    if (!isAuthenticated) return;
    api.staff.getMe().then((res) => {
      if (!res.profile_complete) {
        setStaffData(res.data);
        setShowSetup(true);
      }
      // The role tour is only ever started from ProfileSetup's onComplete
      // below — i.e. once, right when a new user finishes registering.
      // It intentionally does NOT re-check on every sign-in here: an
      // already-onboarded user should never see it again.
    }).catch(() => {
      // Non-fatal — don't block the UI if /staff/me fails
    });
  }, [isAuthenticated]);
  const hasRole = typeof role === "string" && role.trim().length > 0;
  const hasApiBase = typeof apiBaseUrl === "string" && apiBaseUrl.trim().length > 0;

  return (
    <div className="pw-page-surface flex">
      <Sidebar mobileOpen={mobileNavOpen} onMobileClose={() => setMobileNavOpen(false)} />
      <main className="relative z-10 min-h-screen flex-1 bg-transparent lg:ml-64">
        {/* Slim diagnostic top bar */}
        <div className="pw-surface-interactive mx-4 mt-4 flex items-center justify-between px-4 py-2.5 text-xs text-muted-foreground sm:mx-6 sm:px-6">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mr-1 lg:hidden"
              onClick={() => setMobileNavOpen(true)}
            >
              <Menu className="mr-2 h-4 w-4" />
              Menu
            </Button>
            {location.pathname !== "/" && (
              <BackButton fallback="/" className="mr-1 h-7 px-2 text-xs text-muted-foreground hover:text-foreground" />
            )}
            <span className="font-semibold text-foreground">Royan Hospital · RoyanHealth</span>
            <span className="opacity-40">·</span>
            <span>Role: {hasRole ? role : <span className="text-destructive">unavailable</span>}</span>
            {typeof wpUserId === "number" && (
              <span className="opacity-50">(WP User: {wpUserId})</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1 sm:block">
              API: {hasApiBase ? apiBaseUrl : <span className="text-destructive">missing</span>}
            </div>
            <NotificationBell />
          </div>
        </div>
        {/* Page content */}
        <div className="relative z-10 px-3 pb-8 pt-5 sm:px-6">
          <Outlet />
        </div>
      </main>
      <FloatingChat />
      {showSetup && (
        <ProfileSetup
          initialData={staffData}
          onComplete={() => {
            setShowSetup(false);
            startTourIfNeeded(roles[0] ?? "admin", staffData?.tour_state);
          }}
        />
      )}
    </div>
  );
};

export default Layout;
