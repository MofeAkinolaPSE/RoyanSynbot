import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { cn } from "@/lib/utils";

interface AppNotification {
  id: string;
  event: string;
  message: string;
  sub?: string;
  href?: string;
  ts: number;
  read: boolean;
}

const SESSION_KEY = "synbot_notifications";

function eventToNotification(msg: any): AppNotification | null {
  const id = `${msg.event}-${msg.encounter_id ?? msg.patient_id ?? Date.now()}-${Date.now()}`;
  const qn = msg.queue_number ?? msg.encounter_id ?? "?";
  const room = msg.room ?? msg.consulting_room;

  const map: Record<string, { message: string; sub?: string; href?: string }> = {
    encounter_opened: {
      message: `New patient registered`,
      sub: `Ticket ${qn} · ${msg.department ?? ""}`,
      href: "/hospital/front-desk",
    },
    nurse_done: {
      message: `${qn} vitals recorded`,
      sub: "Patient ready for doctor",
      href: "/hospital/queue",
    },
    patient_called: {
      message: `${qn} called${room ? ` → ${room}` : ""}`,
      sub: "Please proceed to the consulting room",
      href: "/hospital/queue",
    },
    consultation_started: {
      message: `${qn} consultation started`,
      sub: room ? `In ${room}` : undefined,
      href: "/hospital/queue",
    },
    lab_result_available: {
      message: "Lab result ready",
      sub: msg.patient_name ?? qn,
      href: "/hospital/lab",
    },
    discharge_completed: {
      message: `${qn} discharged`,
      sub: msg.department ?? "",
      href: "/hospital/queue",
    },
  };

  const entry = map[msg.event];
  if (!entry) return null;

  return { id, event: msg.event, ...entry, ts: Date.now(), read: false };
}

function relativeTime(ts: number): string {
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return new Date(ts).toLocaleDateString();
}

const EVENT_COLORS: Record<string, string> = {
  encounter_opened:      "bg-slate-400",
  nurse_done:            "bg-teal-400",
  patient_called:        "bg-blue-400",
  consultation_started:  "bg-indigo-400",
  lab_result_available:  "bg-purple-400",
  discharge_completed:   "bg-green-400",
};

function loadFromSession(): AppNotification[] {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as AppNotification[]) : [];
  } catch {
    return [];
  }
}

function saveToSession(notifications: AppNotification[]) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(notifications.slice(0, 20)));
  } catch {
    // sessionStorage full or unavailable — silent fail
  }
}

export function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>(loadFromSession);
  const [unread, setUnread] = useState(() => loadFromSession().filter(n => !n.read).length);

  useEffect(() => {
    saveToSession(notifications);
  }, [notifications]);

  const handleMessage = useCallback((msg: any) => {
    const n = eventToNotification(msg);
    if (!n) return;
    setNotifications(prev => {
      const updated = [n, ...prev].slice(0, 20);
      saveToSession(updated);
      return updated;
    });
    setUnread(c => c + 1);
  }, []);

  useRealtimeChannel("encounter_updates", handleMessage);

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    setUnread(0);
  };

  const handleOpen = (isOpen: boolean) => {
    setOpen(isOpen);
    if (isOpen) {
      markAllRead();
    }
  };

  const handleClick = (n: AppNotification) => {
    setOpen(false);
    if (n.href) navigate(n.href);
  };

  return (
    <Popover open={open} onOpenChange={handleOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="relative h-8 w-8 p-0">
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[12px] font-bold text-destructive-foreground leading-none">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="text-sm font-semibold">Notifications</p>
          {notifications.length > 0 && (
            <button
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              onClick={markAllRead}
            >
              <CheckCheck className="h-3.5 w-3.5" /> Mark all read
            </button>
          )}
        </div>

        {notifications.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">
            <Bell className="mx-auto mb-2 h-6 w-6 opacity-30" />
            No notifications yet
          </div>
        ) : (
          <ScrollArea className="max-h-[340px]">
            <div className="divide-y">
              {notifications.map(n => (
                <button
                  key={n.id}
                  className={cn(
                    "w-full text-left px-4 py-3 flex items-start gap-3 transition-colors hover:bg-muted/40",
                    !n.read && "bg-primary/5"
                  )}
                  onClick={() => handleClick(n)}
                >
                  <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", EVENT_COLORS[n.event] ?? "bg-slate-400")} />
                  <div className="flex-1 min-w-0">
                    <p className={cn("text-sm leading-snug", !n.read && "font-medium")}>{n.message}</p>
                    {n.sub && <p className="text-xs text-muted-foreground mt-0.5 truncate">{n.sub}</p>}
                    <p className="text-[13px] text-muted-foreground/70 mt-1">{relativeTime(n.ts)}</p>
                  </div>
                  {!n.read && (
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
                  )}
                </button>
              ))}
            </div>
          </ScrollArea>
        )}
      </PopoverContent>
    </Popover>
  );
}
