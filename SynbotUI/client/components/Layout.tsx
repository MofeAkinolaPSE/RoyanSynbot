import Sidebar from "./Sidebar";
import FloatingChat from "./FloatingChat";
import ProfileSetup from "./ProfileSetup";
import { NotificationBell } from "./NotificationBell";
import { ClockPill } from "./staff/ws-kit";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSynbotConfig } from "@/lib/wp-config";
import { Button } from "@/components/ui/button";
import { BackButton } from "@/components/BackButton";
import { useState, useEffect } from "react";
import { Inbox, Menu } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { api } from "@/lib/api-client";
import { useTour } from "@/components/tour/TourProvider";
import { primaryTourRole } from "@/lib/day-tours";

const Layout = () => {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();
  const { role, apiBaseUrl, wpUserId } = getSynbotConfig();
  const { isAuthenticated, roles } = useAuth();
  const { startTourIfNeeded } = useTour();
  // Staff Workspace inbox (requests, assignments, mentions, HR decisions) - the clinical
  // NotificationBell next to it stays the live feed of queue and lab events.
  const { data: inboxData } = useQuery({
    queryKey: ["ws", "inbox", "all"],
    queryFn: () => api.workspace.inbox("all"),
    refetchInterval: 60_000,
    enabled: isAuthenticated,
  });
  const unread: number = inboxData?.counts?.unread ?? 0;
  const [showSetup, setShowSetup] = useState(false);
  const [staffData, setStaffData] = useState<any>(null);

  useEffect(() => {
    if (!isAuthenticated) return;
    api.staff.getMe().then((res) => {
      if (!res.profile_complete) {
        setStaffData(res.data);
        setShowSetup(true);
      } else {
        // First sign-in of an account whose profile is already complete (made on User Access): the tour runs once,
        // then never again - startTourIfNeeded checks the saved completed / skipped state.
        startTourIfNeeded(primaryTourRole(roles), res.data?.tour_state);
      }
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
              {/* production calls the API on the same server the app loads from (nginx routes it), so no base URL is set */}
              API: {hasApiBase ? apiBaseUrl : "this server"}
            </div>
            <ClockPill />
            <Link to="/workspace?tab=inbox" title="My inbox" aria-label={`My inbox, ${unread} unread`}
              className="relative flex h-7 w-7 items-center justify-center rounded-md border border-border/40 bg-muted/30 hover:bg-muted/60">
              <Inbox className="h-3.5 w-3.5" />
              {unread > 0 && <span className="absolute -right-1.5 -top-1.5 min-w-[16px] rounded-full bg-primary px-1 text-center text-xs font-semibold leading-4 text-primary-foreground">{unread > 99 ? "99+" : unread}</span>}
            </Link>
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
            startTourIfNeeded(primaryTourRole(roles), staffData?.tour_state);
          }}
        />
      )}
    </div>
  );
};

export default Layout;
