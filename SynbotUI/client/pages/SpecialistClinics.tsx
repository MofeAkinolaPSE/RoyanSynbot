import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Stethoscope,
  Plus,
  RefreshCw,
  Save,
  ChevronRight,
  BookOpen,
  FileText,
  Layers,
  CheckCircle2,
  Edit3,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { api } from "@/lib/api-client";

const motionTransitions = {
  fadeInUp: {
    initial: { opacity: 0, y: 18 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, ease: "easeOut" },
  },
};

const SPECIALTIES = [
  "cardiology","ent","ophthalmology","dermatology","orthopaedics",
  "neurology","gastroenterology","urology","pulmonology","endocrinology",
  "psychiatry","paediatrics","oncology","dentistry","general",
];

const SPECIALTY_LABELS: Record<string, string> = {
  cardiology: "Cardiology", ent: "ENT", ophthalmology: "Ophthalmology",
  dermatology: "Dermatology", orthopaedics: "Orthopaedics", neurology: "Neurology",
  gastroenterology: "Gastroenterology", urology: "Urology", pulmonology: "Pulmonology",
  endocrinology: "Endocrinology", psychiatry: "Psychiatry", paediatrics: "Paediatrics",
  oncology: "Oncology", dentistry: "Dentistry", general: "General",
};

const SPECIALTY_COLORS: Record<string, string> = {
  cardiology: "bg-red-50 text-red-700 border-red-200",
  ent: "bg-orange-50 text-orange-700 border-orange-200",
  ophthalmology: "bg-yellow-50 text-yellow-700 border-yellow-200",
  dermatology: "bg-lime-50 text-lime-700 border-lime-200",
  orthopaedics: "bg-green-50 text-green-700 border-green-200",
  neurology: "bg-teal-50 text-teal-700 border-teal-200",
  gastroenterology: "bg-cyan-50 text-cyan-700 border-cyan-200",
  urology: "bg-blue-50 text-blue-700 border-blue-200",
  pulmonology: "bg-indigo-50 text-indigo-700 border-indigo-200",
  endocrinology: "bg-violet-50 text-violet-700 border-violet-200",
  psychiatry: "bg-purple-50 text-purple-700 border-purple-200",
  paediatrics: "bg-pink-50 text-pink-700 border-pink-200",
  oncology: "bg-rose-50 text-rose-700 border-rose-200",
  dentistry: "bg-amber-50 text-amber-700 border-amber-200",
  general: "bg-gray-50 text-gray-700 border-gray-200",
};

type AppTab = "templates" | "notes" | "write";

// ── Dynamic field renderer ────────────────────────────────────────────────
function FieldInput({
  field,
  value,
  onChange,
}: {
  field: any;
  value: any;
  onChange: (key: string, val: any) => void;
}) {
  const { key, label, type, options } = field;
  if (type === "textarea") {
    return (
      <div>
        <Label className="text-xs mb-1 block">{label}</Label>
        <Textarea
          value={value ?? ""}
          onChange={e => onChange(key, e.target.value)}
          className="text-sm min-h-[64px]"
          placeholder={label}
        />
      </div>
    );
  }
  if (type === "boolean") {
    return (
      <div className="flex items-center gap-3">
        <Label className="text-xs flex-1">{label}</Label>
        <Switch
          checked={!!value}
          onCheckedChange={v => onChange(key, v)}
        />
      </div>
    );
  }
  if (type === "select" && options) {
    return (
      <div>
        <Label className="text-xs mb-1 block">{label}</Label>
        <Select value={value ?? ""} onValueChange={v => onChange(key, v)}>
          <SelectTrigger className="h-9 text-sm"><SelectValue placeholder={label} /></SelectTrigger>
          <SelectContent>
            {(options as string[]).map(o => (
              <SelectItem key={o} value={o}>{o}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }
  return (
    <div>
      <Label className="text-xs mb-1 block">{label}</Label>
      <Input
        type={type === "number" ? "number" : "text"}
        value={value ?? ""}
        onChange={e => onChange(key, type === "number" ? Number(e.target.value) : e.target.value)}
        className="h-9 text-sm"
        placeholder={label}
      />
    </div>
  );
}

// ── Template card ─────────────────────────────────────────────────────────
function TemplateCard({
  tmpl,
  onWrite,
}: {
  tmpl: any;
  onWrite: (tmpl: any) => void;
}) {
  const color = SPECIALTY_COLORS[tmpl.specialty] ?? SPECIALTY_COLORS.general;
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="pt-4 pb-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="outline" className={`text-[10px] ${color}`}>
                {SPECIALTY_LABELS[tmpl.specialty] ?? tmpl.specialty}
              </Badge>
            </div>
            <p className="text-sm font-semibold">{tmpl.template_name}</p>
            {tmpl.default_order_sets?.length > 0 && (
              <p className="text-xs text-muted-foreground mt-1 truncate">
                Orders: {(tmpl.default_order_sets as string[]).join(" · ")}
              </p>
            )}
          </div>
          <Button size="sm" variant="outline" className="shrink-0" onClick={() => onWrite(tmpl)}>
            <Edit3 className="h-3.5 w-3.5 mr-1.5" /> Write Note
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Note writer ───────────────────────────────────────────────────────────
function NoteWriter({
  template,
  onClose,
  onSaved,
}: {
  template: any;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const qc = useQueryClient();

  const [patientId,   setPatientId]   = useState("");
  const [encounterId, setEncounterId] = useState("");
  const [icd10,       setIcd10]       = useState("");
  const [noteData,    setNoteData]    = useState<Record<string, any>>({});

  const submitMut = useMutation({
    mutationFn: () => api.specialist.submitNote({
      patient_id:   Number(patientId),
      encounter_id: encounterId ? Number(encounterId) : undefined,
      template_id:  template.id,
      specialty:    template.specialty,
      note_data:    noteData,
      icd10_codes:  icd10 ? icd10.split(",").map(s => s.trim()).filter(Boolean) : undefined,
      assessment:   noteData.assessment,
      plan:         noteData.plan,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["specialist-notes"] });
      toast({ title: "Note saved", description: `${template.template_name} note recorded.` });
      onSaved();
    },
    onError: (e: any) => toast({ variant: "destructive", title: "Save failed", description: e?.message }),
  });

  const setField = (key: string, val: any) => setNoteData(prev => ({ ...prev, [key]: val }));

  const fields: any[] = template.fields ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b">
        <Badge variant="outline" className={`${SPECIALTY_COLORS[template.specialty] ?? ""} text-xs`}>
          {SPECIALTY_LABELS[template.specialty]}
        </Badge>
        <span className="text-sm font-medium">{template.template_name}</span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Patient ID *</Label>
          <Input value={patientId} onChange={e => setPatientId(e.target.value)} className="h-9" placeholder="Patient ID" />
        </div>
        <div>
          <Label className="text-xs">Encounter ID</Label>
          <Input value={encounterId} onChange={e => setEncounterId(e.target.value)} className="h-9" placeholder="Encounter ID" />
        </div>
      </div>
      <div>
        <Label className="text-xs">ICD-10 Codes (comma-separated)</Label>
        <Input value={icd10} onChange={e => setIcd10(e.target.value)} className="h-9" placeholder="I10, J45.0" />
      </div>

      <div className="max-h-[400px] overflow-y-auto space-y-3 pr-1">
        {fields.map((f: any) => (
          <FieldInput key={f.key} field={f} value={noteData[f.key]} onChange={setField} />
        ))}
      </div>

      {template.default_order_sets?.length > 0 && (
        <div className="rounded-lg bg-muted/50 p-3">
          <p className="text-xs font-medium text-muted-foreground mb-1.5">Default Order Sets</p>
          <div className="flex flex-wrap gap-1.5">
            {(template.default_order_sets as string[]).map(o => (
              <Badge key={o} variant="secondary" className="text-[10px]">{o}</Badge>
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
        <Button
          size="sm"
          onClick={() => submitMut.mutate()}
          disabled={submitMut.isPending || !patientId}
        >
          <Save className="h-3.5 w-3.5 mr-1.5" />
          {submitMut.isPending ? "Saving…" : "Save Note"}
        </Button>
      </div>
    </div>
  );
}

// ── Notes list tab ────────────────────────────────────────────────────────
function NotesTab() {
  const [filterSpec, setFilterSpec] = useState("all");
  const [viewNote,   setViewNote]   = useState<any>(null);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["specialist-notes", filterSpec],
    queryFn:  () => api.specialist.listNotes({ specialty: filterSpec !== "all" ? filterSpec : undefined }),
  });
  const notes = data?.notes ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Select value={filterSpec} onValueChange={setFilterSpec}>
          <SelectTrigger className="h-8 w-44 text-sm"><SelectValue placeholder="Specialty" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All specialties</SelectItem>
            {SPECIALTIES.map(s => (
              <SelectItem key={s} value={s} className="capitalize">{SPECIALTY_LABELS[s]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/40 border-b">
              {["ID","Patient","Encounter","Specialty","Assessment","By","Date",""].map(h => (
                <th key={h} className="px-4 py-2.5 text-left font-medium text-muted-foreground text-xs">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {notes.length === 0 && !isFetching && (
              <tr><td colSpan={8} className="text-center py-10 text-muted-foreground text-sm">No notes found.</td></tr>
            )}
            {notes.map((n: any) => (
              <tr key={n.id} className="border-b hover:bg-muted/20">
                <td className="px-4 py-2.5 text-xs text-muted-foreground">#{n.id}</td>
                <td className="px-4 py-2.5">{n.patient_id}</td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground">{n.encounter_id ?? "—"}</td>
                <td className="px-4 py-2.5">
                  <Badge variant="outline" className={`text-[10px] ${SPECIALTY_COLORS[n.specialty] ?? ""}`}>
                    {SPECIALTY_LABELS[n.specialty] ?? n.specialty}
                  </Badge>
                </td>
                <td className="px-4 py-2.5 max-w-[200px] truncate text-xs">{n.assessment ?? "—"}</td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground">{n.noted_by}</td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground">
                  {n.noted_at ? new Date(n.noted_at).toLocaleDateString() : "—"}
                </td>
                <td className="px-4 py-2.5">
                  <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setViewNote(n)}>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Note detail dialog */}
      <Dialog open={!!viewNote} onOpenChange={() => setViewNote(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Specialist Note #{viewNote?.id}</DialogTitle>
          </DialogHeader>
          {viewNote && (
            <div className="space-y-3 text-sm max-h-[480px] overflow-y-auto">
              <div className="grid grid-cols-3 gap-3 text-xs text-muted-foreground">
                <div><span className="font-medium text-foreground">Patient:</span> {viewNote.patient_id}</div>
                <div><span className="font-medium text-foreground">Encounter:</span> {viewNote.encounter_id ?? "—"}</div>
                <div><span className="font-medium text-foreground">By:</span> {viewNote.noted_by}</div>
              </div>
              {viewNote.icd10_codes?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {viewNote.icd10_codes.map((c: string) => (
                    <Badge key={c} variant="outline" className="text-[10px]">{c}</Badge>
                  ))}
                </div>
              )}
              {viewNote.assessment && (
                <div>
                  <p className="text-xs font-semibold mb-1">Assessment</p>
                  <p className="text-sm bg-muted/50 rounded p-2">{viewNote.assessment}</p>
                </div>
              )}
              {viewNote.plan && (
                <div>
                  <p className="text-xs font-semibold mb-1">Plan</p>
                  <p className="text-sm bg-muted/50 rounded p-2">{viewNote.plan}</p>
                </div>
              )}
              {viewNote.note_data && Object.keys(viewNote.note_data).length > 0 && (
                <div>
                  <p className="text-xs font-semibold mb-2">Full Note Data</p>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(viewNote.note_data).map(([k, v]) => (
                      <div key={k} className="bg-muted/40 rounded p-2">
                        <p className="text-[10px] text-muted-foreground capitalize">{k.replace(/_/g, " ")}</p>
                        <p className="text-xs font-medium">{String(v)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────
export default function SpecialistClinics() {
  const { toast } = useToast();
  const qc        = useQueryClient();

  const [tab,           setTab]          = useState<AppTab>("templates");
  const [filterSpec,    setFilterSpec]   = useState("all");
  const [activeTemplate, setActiveTemplate] = useState<any>(null);
  const [showSeeded,    setShowSeeded]   = useState(false);

  const { data: tplData, isFetching: tplLoading, refetch: refetchTpl } = useQuery({
    queryKey: ["specialist-templates", filterSpec],
    queryFn:  () => api.specialist.listTemplates(filterSpec !== "all" ? filterSpec : undefined),
  });
  const templates = tplData?.templates ?? [];

  const seedMut = useMutation({
    mutationFn: () => api.specialist.seedTemplates(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["specialist-templates"] });
      setShowSeeded(true);
      toast({
        title: "Templates seeded",
        description: `${res.inserted?.length ?? 0} inserted, ${res.skipped?.length ?? 0} already existed.`,
      });
    },
    onError: (e: any) => toast({ variant: "destructive", title: "Seed failed", description: e?.message }),
  });

  const handleWriteDone = () => {
    setActiveTemplate(null);
    setTab("notes");
  };

  const tabs: { key: AppTab; label: string; icon: React.ElementType }[] = [
    { key: "templates", label: "Templates",  icon: Layers },
    { key: "notes",     label: "Notes",      icon: FileText },
  ];

  return (
    <motion.div {...motionTransitions.fadeInUp} className="space-y-4 p-4 md:p-6">
      <AlertBanner />

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Specialist Clinics</h1>
          <p className="text-sm text-muted-foreground">14-specialty structured note templates — TIU module</p>
        </div>
        <div className="flex gap-2">
          {templates.length === 0 && !tplLoading && (
            <Button size="sm" variant="outline" onClick={() => seedMut.mutate()} disabled={seedMut.isPending}>
              <BookOpen className="h-4 w-4 mr-1.5" />
              {seedMut.isPending ? "Seeding…" : "Seed Built-in Templates"}
            </Button>
          )}
          {showSeeded && (
            <Badge className="bg-green-100 text-green-700 border border-green-200">
              <CheckCircle2 className="h-3 w-3 mr-1" /> 14 templates loaded
            </Badge>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1.5">
        {tabs.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.key ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              <Icon className="h-3.5 w-3.5" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "templates" && (
        <div className="space-y-3">
          {/* Specialty filter */}
          <div className="flex flex-wrap gap-1.5">
            {["all", ...SPECIALTIES].map(s => (
              <button
                key={s}
                onClick={() => setFilterSpec(s)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  filterSpec === s
                    ? "bg-primary text-primary-foreground"
                    : `border ${SPECIALTY_COLORS[s] ?? "bg-muted text-muted-foreground border-border"} hover:opacity-80`
                }`}
              >
                {s === "all" ? "All Specialties" : SPECIALTY_LABELS[s]}
              </button>
            ))}
          </div>

          <div className="flex justify-end">
            <Button size="sm" variant="outline" onClick={() => refetchTpl()} disabled={tplLoading}>
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${tplLoading ? "animate-spin" : ""}`} /> Refresh
            </Button>
          </div>

          {templates.length === 0 && !tplLoading && (
            <div className="text-center py-12 text-sm text-muted-foreground">
              No templates found. Click <strong>Seed Built-in Templates</strong> to load all 14 specialty templates.
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {templates.map((t: any) => (
              <TemplateCard key={t.id} tmpl={t} onWrite={(tmpl) => { setActiveTemplate(tmpl); setTab("write" as AppTab); }} />
            ))}
          </div>
        </div>
      )}

      {(tab as string) === "write" && activeTemplate && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Stethoscope className="h-4 w-4 text-muted-foreground" />
              New Specialist Note
            </CardTitle>
          </CardHeader>
          <CardContent>
            <NoteWriter
              template={activeTemplate}
              onClose={() => setTab("templates")}
              onSaved={handleWriteDone}
            />
          </CardContent>
        </Card>
      )}

      {tab === "notes" && <NotesTab />}
    </motion.div>
  );
}
