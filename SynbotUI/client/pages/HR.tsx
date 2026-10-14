/**
 * Human Resources, on live data: who is online and on the clock, hours this week per person
 * (saved timesheets + clocks still running), the directory built from User Access, timesheet
 * review, the shift roster, leave and the monthly payroll run that feeds Roy Books.
 * The hours come from each person's work clock in their Staff Workspace - nothing is typed twice.
 *
 * Tabs follow ?tab= so links from the workspace ("Leave to decide", "Payroll to approve") land here.
 */
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { UserPlus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/workspace/PageHeader";
import { useAuth } from "@/components/AuthProvider";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { AddPersonSheet, DirectoryPanel, OverviewPanel, PersonSheet, TimesheetsPanel } from "@/components/hr/hr-panels";
import { HRShiftsPanels } from "./HRShifts";

const TABS: [string, string][] = [
  ["overview", "Overview"], ["directory", "Staff directory"], ["timesheets", "Timesheets"],
  ["shifts", "Shift roster"], ["leave", "Leave"], ["payroll", "Payroll"],
];

const HR = () => {
  const qc = useQueryClient();
  const { roles } = useAuth();
  const canEdit = roles.some((r) => r === "admin" || r === "hr");
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? (params.get("tab") as string) : "overview";
  const [person, setPerson] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["hr"] });
    ["hr-stats", "hr-leave", "hr-shifts", "dashboard-workforce"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  };
  useRealtimeChannel("staff_updates", refresh);
  useRealtimeChannel("workspace_updates", (m: any) => { if (m?.event === "clock" || m?.event === "leave") refresh(); });
  const go = (t: string) => { params.set("tab", t); setParams(params, { replace: true }); };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={Users} title="Human Resources"
        subtitle="Live attendance, hours, leave and payroll - from what staff record in their workspace."
        actions={canEdit ? <Button size="sm" variant="outline" onClick={() => setAdding(true)}><UserPlus className="mr-2 h-4 w-4" />Add staff record</Button> : undefined} />
      <Tabs value={tab} onValueChange={go}>
        <TabsList className="mb-2 h-auto flex-wrap">
          {TABS.map(([k, l]) => <TabsTrigger key={k} value={k}>{l}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="overview"><OverviewPanel onPerson={setPerson} gotoTimesheets={() => go("timesheets")} /></TabsContent>
        <TabsContent value="directory"><DirectoryPanel onPerson={setPerson} /></TabsContent>
        <TabsContent value="timesheets"><TimesheetsPanel canEdit={canEdit} onPerson={setPerson} /></TabsContent>
        {/* Shift roster / Leave / Payroll: contributes its own TabsContent (resolved through Tabs context). */}
        <HRShiftsPanels />
      </Tabs>
      <PersonSheet personKey={person} onClose={() => setPerson(null)} canEdit={canEdit} />
      <AddPersonSheet open={adding} onOpenChange={(v) => { setAdding(v); if (!v) refresh(); }} />
    </div>
  );
};

export default HR;
