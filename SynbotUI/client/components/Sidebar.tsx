import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTheme } from "next-themes";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  LogOut,
  MoreVertical,
  Sun,
  Moon,
  Settings,
  Compass,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "./AuthProvider";
import { api } from "@/lib/api-client";
import { NAV_ITEMS, type NavItem } from "@/lib/nav-items";
import { canViewByRoles, menuChildren } from "@/lib/nav-access";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useTour } from "@/components/tour/TourProvider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type SidebarProps = {
  mobileOpen: boolean;
  onMobileClose: () => void;
};

const Sidebar = ({ mobileOpen, onMobileClose }: SidebarProps) => {
  const location = useLocation();
  const { roles, isLoading: authLoading, logout } = useAuth();
  const { startTour, hasTour } = useTour();
  const tourRole = roles?.[0] ?? "admin";

  // Track which collapsible groups are open
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  // Live badge counts for clinical nav items
  const { data: queueData } = useQuery({
    queryKey: ["sidebar-queue-badge"],
    queryFn: () => api.hospital.queue.list({ status: "patient_registered" }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const { data: labData } = useQuery({
    queryKey: ["sidebar-lab-badge"],
    queryFn: () => api.hospital.lab.listOrders({ status: "ordered" }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const queueCount: number = queueData?.count ?? 0;
  const labCount: number = labData?.count ?? 0;

  const toggleGroup = (label: string) => {
    setOpenGroups((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  // A link may carry a query (Finance › Scancare Books is /finance/books?company=SCN): match on the path.
  const isActive = (path: string) => location.pathname === path.split("?")[0];
  const isActiveGroup = (paths: string[]) =>
    paths.some((p) => location.pathname.startsWith(p.split("?")[0]));

  // NAV_ITEMS is the single shared source of truth (also consumed by tour-config.ts).
  // Live queue/lab badge counts are injected here at render time.
  const countFor = (k?: string) => (k === "queue" ? queueCount : k === "lab" ? labCount : 0);
  const navItems: NavItem[] = NAV_ITEMS.map((item) =>
    item.badgeKey ? { ...item, badge: countFor(item.badgeKey) > 0 ? String(countFor(item.badgeKey)) : undefined } : item);

  const canView = (allowed?: string[]) => authLoading || canViewByRoles(roles, allowed);

  // A group is visible if the user can see the group itself OR any child that
  // declares its own roles. Filtering on the parent alone would hide Pharmacy
  // from quality_assurance, whose only pharmacy page is the QC child.
  // A folder shows when at least one of its children shows (by access and by menu placement);
  // a page shows by its own roles.
  const kidsOf = (item: NavItem) => (authLoading ? item.children ?? [] : menuChildren(roles, item));
  const visibleNavItems = navItems.filter((item) => (item.children ? kidsOf(item).length > 0 : canView(item.roles)));

  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  // Derive user initials from roles/auth — fallback to "PW"
  const userRole = roles[0] ?? "user";
  const initials = userRole.slice(0, 2).toUpperCase();

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={cn(
          "fixed inset-0 z-20 bg-black/40 transition-opacity lg:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onMobileClose}
      />

      {/* Sidebar panel */}
      <div
        className={cn(
          "fixed left-0 top-0 z-30 flex h-screen w-64 flex-col border-r border-sidebar-border/70 bg-sidebar/95 text-sidebar-foreground backdrop-blur-lg transition-transform duration-300",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          "lg:translate-x-0",
        )}
      >
        {/* Logo/Header */}
        <div className="border-b border-sidebar-border/80 px-4 py-3.5">
          <div
            className="relative overflow-hidden rounded-xl px-3 py-2"
            style={{
              background: "linear-gradient(135deg, rgba(19,167,224,0.07) 0%, rgba(201,162,75,0.05) 100%)",
              border: "1px solid rgba(201,162,75,0.22)",
              boxShadow: "0 0 18px rgba(19,167,224,0.06), 0 0 22px rgba(201,162,75,0.06), inset 0 1px 0 rgba(255,255,255,0.06)",
            }}
          >
            {/* Radial highlight shimmer */}
            <div
              className="pointer-events-none absolute inset-0"
              aria-hidden
              style={{
                background: "radial-gradient(ellipse 70% 55% at 50% 0%, rgba(255,255,255,0.07) 0%, transparent 70%)",
              }}
            />
            <img
              src="/royan-logo.png"
              alt="Royan Hospital"
              className="relative w-full h-auto object-contain"
              style={{
                maxHeight: "48px",
                filter: "drop-shadow(0 2px 8px rgba(19,167,224,0.24)) drop-shadow(0 0 2px rgba(255,255,255,0.15))",
              }}
            />
            {/* Thin gold rule — the app's one everyday gold touch, kept small */}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, #C9A24B 50%, transparent)" }} />
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-3 scrollbar-thin">
          <div className="space-y-0.5">
            {visibleNavItems.map((item) => {
              const Icon = item.icon;
              const hasChildren = !!item.children;
              const groupOpen = !!openGroups[item.label];
              const childActive = hasChildren
                ? isActiveGroup(item.children!.map((c) => c.href))
                : false;
              const itemActive = !hasChildren && isActive(item.href ?? "");

              if (hasChildren) {
                return (
                  <Collapsible
                    key={item.label}
                    open={groupOpen}
                    onOpenChange={() => toggleGroup(item.label)}
                  >
                    <CollapsibleTrigger asChild>
                      <button
                        className={cn(
                          "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 ease-out",
                          childActive
                            ? "bg-sidebar-accent/70 text-sidebar-accent-foreground"
                            : "text-sidebar-foreground/80 hover:bg-sidebar-accent/40 hover:text-sidebar-foreground",
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className="flex-1 text-left">{item.label}</span>
                        <ChevronDown
                          className={cn(
                            "h-3.5 w-3.5 shrink-0 opacity-50 transition-transform duration-200",
                            groupOpen && "rotate-180",
                          )}
                        />
                      </button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
                      <div className="ml-3 mt-0.5 space-y-0.5 border-l border-sidebar-border/50 pl-3 pb-1">
                        {kidsOf(item)
                          .map((child) => (
                          <Link
                            key={child.href}
                            to={child.href}
                            onClick={onMobileClose}
                            className={cn(
                              "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-all duration-150",
                              isActive(child.href)
                                ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium shadow-elevation-1"
                                : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                            )}
                          >
                            <span className="h-1 w-1 rounded-full bg-current opacity-50" />
                            <span className="flex-1">{child.label}</span>
                            {countFor(child.badgeKey) > 0 && (
                              <span className="rounded-full bg-orange-500 px-1.5 text-xs font-semibold text-white">{countFor(child.badgeKey)}</span>
                            )}
                          </Link>
                        ))}
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                );
              }

              return (
                <Link
                  key={item.label}
                  to={item.href ?? "/"}
                  onClick={onMobileClose}
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 ease-out",
                    itemActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-elevation-1"
                      : "text-sidebar-foreground/80 hover:bg-sidebar-accent/40 hover:text-sidebar-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="flex-1">{item.label}</span>
                  {item.aiPulse && (
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
                    </span>
                  )}
                  {item.badge && !item.aiPulse && (
                    <span className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-semibold",
                      item.badge === "AI"
                        ? "bg-gradient-primary text-primary-foreground"
                        : "bg-orange-500 text-white",
                    )}>
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </nav>

        {/* User Profile Footer */}
        <div className="border-t border-sidebar-border/80 p-3">
          <div className="flex items-center gap-2 rounded-xl px-2 py-2 hover:bg-sidebar-accent/40 transition-colors duration-150">
            {/* Avatar */}
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-primary text-xs font-bold text-primary-foreground shadow-elevation-1">
              {initials}
            </div>
            {/* Name + role */}
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-sm font-medium leading-tight">
                Roy
              </span>
              <span className="truncate text-xs capitalize text-sidebar-foreground/50 leading-tight">
                {userRole}
              </span>
            </div>
            {/* Actions dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="ml-auto flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-sidebar-foreground/50 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground transition-colors"
                  aria-label="User options"
                >
                  <MoreVertical className="h-4 w-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                side="top"
                sideOffset={8}
                className="w-48"
              >
                <DropdownMenuItem asChild>
                  <Link to="/settings">
                    <Settings className="mr-2 h-4 w-4" />
                    Settings
                  </Link>
                </DropdownMenuItem>
                {hasTour(tourRole) && (
                  <DropdownMenuItem onClick={() => startTour(tourRole)}>
                    <Compass className="mr-2 h-4 w-4" />
                    Take the tour again
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem
                  onClick={() => setTheme(isDark ? "light" : "dark")}
                >
                  {isDark ? (
                    <Sun className="mr-2 h-4 w-4" />
                  ) : (
                    <Moon className="mr-2 h-4 w-4" />
                  )}
                  {isDark ? "Light mode" : "Dark mode"}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={() => logout()}
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </>
  );
};

export default Sidebar;
