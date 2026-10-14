/**
 * My Workspace - every member of staff's home: their day, their work, requests and messages with
 * colleagues, the work clock, leave and their own progress. Replaces the separate Staff Dashboard,
 * Time Tracker and Collaboration pages (their old links open the matching tab here).
 * Spec: backend/docs/Staff-workspace. API: backend/src/routers/staff_workspace.py.
 *
 * Doctors and nurses do not get a separate page: their clinical home (My Dashboard / the Nursing
 * Station) is the first tab of this same view, so their patients, their day, tasks, inbox and
 * messages live in one place. /workspace sends them there, keeping ?tab= so old links still land.
 */
import { ReactNode, useMemo, useState } from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlarmClock, BarChart3, CalendarOff, HandHelping, Home, Inbox, ListChecks, Loader2, MessageSquare, Settings2, StickyNote, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api-client";
import {
  ChatSheet, EscalationSheet, LeaveSheet, NewRequestSheet, NewTaskDefaults, NewTaskSheet, RequestDefaults, RequestSheet, TaskSheet, useWorkspaceLive,
} from "@/components/staff/ws-kit";
import { useAuth } from "@/components/AuthProvider";
import { DayPanel, InboxPanel, MessagesPanel, ProgressPanel, TeamPanel, WorkPanel, WsActions, WsCtx } from "@/components/staff/ws-panels";

const TABS = [
  { key: "day", label: "My Day", icon: Home },
  { key: "work", label: "My Work", icon: ListChecks },
  { key: "inbox", label: "Inbox", icon: Inbox },
  { key: "messages", label: "Messages", icon: MessageSquare },
  { key: "team", label: "Team", icon: Users },
  { key: "progress", label: "Progress", icon: BarChart3 },
];

/** A clinical tab placed before the workspace tabs (the doctor's patients, the nursing station). */
export type LeadTab = { key: string; label: string; icon: any; render: () => ReactNode };

/** Where a person's combined home is, if their role has one. */
export function clinicalHome(roles: string[]): string | null {
  if (roles.includes("doctor")) return "/hospital/doctor";
  if (roles.includes("nurse")) return "/hospital/nurse";
  return null;
}

export default function StaffWorkspace() {
  const { roles } = useAuth();
  const loc = useLocation();
  const home = clinicalHome(roles);
  if (home) return <Navigate to={`${home}${loc.search}`} replace />;
  return <WorkspaceView />;
}

export function WorkspaceView({ lead = [], title }: { lead?: LeadTab[]; title?: string }) {
  useWorkspaceLive();
  const [params, setParams] = useSearchParams();
  const prefsQ = useQuery({ queryKey: ["ws", "prefs"], queryFn: () => api.workspace.prefs(), staleTime: 300_000 });
  const prefs = prefsQ.data ?? {};
  const allTabs = [...lead.map((l) => ({ key: l.key, label: l.label, icon: l.icon })), ...TABS];
  const asked = params.get("tab");
  const tab = asked && allTabs.some((t) => t.key === asked) ? asked : lead[0]?.key || prefs.default_tab || "day";
  const leadTab = lead.find((l) => l.key === tab);
  const day = useQuery({ queryKey: ["ws", "day"], queryFn: () => api.workspace.day(), refetchInterval: 120_000 });

  const [taskId, setTaskId] = useState<string | null>(null);
  const [newTask, setNewTask] = useState<NewTaskDefaults | null>(null);
  const [ask, setAsk] = useState<RequestDefaults | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [chat, setChat] = useState<{ id: string; name?: string } | null>(null);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const { roles } = useAuth();
  const canSetRules = roles.some((r) => ["admin", "management", "hr"].includes(r));

  const goto = (t: string) => { params.set("tab", t); params.delete("with"); setParams(params, { replace: true }); };
  const actions: WsActions = useMemo(() => ({
    openTask: (id) => setTaskId(id),
    newTask: (d) => setNewTask(d ?? {}),
    ask: (d) => setAsk(d ?? {}),
    openRequest: (id) => setRequestId(id),
    chat: (id, name) => (id === "team" ? goto("messages") : setChat({ id, name })),
    goto,
  }), [params]);  // eslint-disable-line react-hooks/exhaustive-deps

  const d = day.data;
  const c = d?.counts ?? {};
  const badge: Record<string, number> = { inbox: (c.unread ?? 0) + (c.to_answer ?? 0), messages: c.unread_messages ?? 0, work: c.overdue ?? 0 };

  const savePref = (k: string, v: any) => api.workspace.savePrefs({ [k]: v }).then(() => prefsQ.refetch());

  return (
    <WsCtx.Provider value={actions}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{d ? `${d.greeting}, ${d.me?.name?.split(" ")[0] ?? ""}` : title ?? "My Workspace"}</h1>
            <p className="text-sm text-muted-foreground">
              {new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}
              {d?.me?.department ? ` · ${d.me.job_title ? d.me.job_title + ", " : ""}${d.me.unit || d.me.department}` : ""}
              {d ? ` · ${c.due_today ? `${c.due_today} thing${c.due_today === 1 ? "" : "s"} due today` : "nothing due today"}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setNewTask({ kind: "task" })}><ListChecks className="mr-1.5 h-4 w-4" />Task</Button>
            <Button size="sm" variant="outline" onClick={() => setNewTask({ kind: "reminder" })}><AlarmClock className="mr-1.5 h-4 w-4" />Reminder</Button>
            <Button size="sm" variant="outline" onClick={() => setNewTask({ kind: "note" })}><StickyNote className="mr-1.5 h-4 w-4" />Note</Button>
            <Button size="sm" variant="outline" onClick={() => setAsk({})}><HandHelping className="mr-1.5 h-4 w-4" />Ask</Button>
            <Button size="sm" variant="outline" onClick={() => goto("messages")}><MessageSquare className="mr-1.5 h-4 w-4" />Message</Button>
            <Button size="sm" variant="outline" onClick={() => setLeaveOpen(true)}><CalendarOff className="mr-1.5 h-4 w-4" />Leave</Button>
            <div className="relative">
              <Button size="sm" variant="ghost" title="Customise" onClick={() => setPrefsOpen((v) => !v)}><Settings2 className="h-4 w-4" /></Button>
              {prefsOpen && <div className="fixed inset-0 z-30" onClick={() => setPrefsOpen(false)} />}
              {prefsOpen && <div className="absolute right-0 z-40 mt-1 w-64 space-y-3 rounded-lg border bg-card p-3 text-sm shadow-lg">
                <div className="font-medium">My workspace</div>
                {[["show_operational", "Show items for my role"], ["show_journal", "Show my day so far"]].map(([k, l]) => (
                  <label key={k} className="flex items-center justify-between gap-2"><span>{l}</span>
                    <Switch checked={prefs[k] !== false} onCheckedChange={(v) => savePref(k, v)} /></label>
                ))}
                <label className="flex items-center justify-between gap-2"><span>Open on</span>
                  <select value={prefs.default_tab ?? "day"} onChange={(e) => savePref("default_tab", e.target.value)} className="h-8 rounded-md border bg-background px-2 text-xs">
                    {TABS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                  </select></label>
                {canSetRules && (
                  <Button size="sm" variant="outline" className="w-full" onClick={() => { setPrefsOpen(false); setRulesOpen(true); }}>Escalation rules…</Button>
                )}
                <label className="flex items-center justify-between gap-2"><span>Sort tasks</span>
                  <select value={prefs.task_order ?? "due"} onChange={(e) => savePref("task_order", e.target.value)} className="h-8 rounded-md border bg-background px-2 text-xs">
                    <option value="due">By due date</option><option value="priority">By priority</option>
                  </select></label>
              </div>}
            </div>
          </div>
        </div>

        <div className="flex gap-1 overflow-x-auto border-b">
          {allTabs.map((t) => (
            <button key={t.key} onClick={() => goto(t.key)}
              className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm ${tab === t.key ? "border-primary font-medium text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
              <t.icon className="h-4 w-4" />{t.label}
              {badge[t.key] > 0 && <Badge variant={t.key === "work" ? "destructive" : "default"} className="h-5 px-1.5 text-xs">{badge[t.key]}</Badge>}
            </button>
          ))}
        </div>

        {leadTab && leadTab.render()}
        {tab === "day" && (day.isLoading ? <Loader2 className="mx-auto mt-10 h-6 w-6 animate-spin text-muted-foreground" /> :
          day.error ? <p className="text-sm text-destructive">Could not load your day: {(day.error as any)?.message}</p> :
            <DayPanel day={d} prefs={prefs} />)}
        {tab === "work" && <WorkPanel prefs={prefs} />}
        {tab === "inbox" && <InboxPanel />}
        {tab === "messages" && <MessagesPanel initial={params.get("with")} />}
        {tab === "team" && <TeamPanel />}
        {tab === "progress" && <ProgressPanel />}
      </div>

      <TaskSheet taskId={taskId} onClose={() => setTaskId(null)} onAsk={(t) => { setTaskId(null); setAsk({ task_id: t.id, subject: t.title }); }} />
      <NewTaskSheet open={!!newTask} onOpenChange={(v) => !v && setNewTask(null)} defaults={newTask ?? undefined} />
      <NewRequestSheet open={!!ask} onOpenChange={(v) => !v && setAsk(null)} defaults={ask ?? undefined} />
      <RequestSheet requestId={requestId} onClose={() => setRequestId(null)} />
      <ChatSheet withId={chat?.id ?? null} name={chat?.name} onClose={() => setChat(null)} />
      <LeaveSheet open={leaveOpen} onOpenChange={setLeaveOpen} />
      {canSetRules && <EscalationSheet open={rulesOpen} onOpenChange={setRulesOpen} canRun={roles.some((r) => r === "admin" || r === "management")} />}
    </WsCtx.Provider>
  );
}
