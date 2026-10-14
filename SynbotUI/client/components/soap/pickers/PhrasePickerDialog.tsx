import { useEffect, useMemo, useState } from "react";
import { Loader2, Search } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { parsePhraseTemplate, countPlaceholders, defaultValuesFor } from "@/lib/phrase-template";
import { PhraseFillRow, renderStaged } from "./PhraseFillRow";

export interface PhraseItem {
  id: string | number;
  text: string;
  /** Optional grouping label used by composeMode="grouped". */
  group?: string;
}

export interface PhraseGroup {
  id: string;
  label: string;
  sublabel?: string;
  /** Badge on the group row, e.g. "personal". */
  tag?: string;
  /** Undefined until lazily loaded. */
  items?: PhraseItem[];
}

export type ComposeMode = "lines" | "grouped";

/**
 * Generic two-pane phrase picker. Deliberately knows NOTHING about the API —
 * adapters (NoteTemplatePicker, ExamFindingPicker) fetch and map into
 * PhraseGroup[], then render this.
 *
 * Left  = groups (templates, or organ systems)
 * Right = selectable phrases for the highlighted group
 * Below = staged tray, where "??" and {token} blanks get filled before insert
 *
 * composeMode:
 *   "lines"   -> one phrase per line (note templates)
 *   "grouped" -> "Respiratory: cough, dyspnoea." (exam findings, where a
 *                clinician ticks several findings under one system)
 */
export function PhrasePickerDialog({
  open,
  onOpenChange,
  title,
  description,
  groups,
  activeGroupId,
  onActiveGroupChange,
  isLoadingGroups,
  isLoadingItems,
  onSearchItems,
  composeMode = "lines",
  onInsert,
  extraActions,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: string;
  groups: PhraseGroup[];
  activeGroupId: string | null;
  onActiveGroupChange: (id: string) => void;
  isLoadingGroups?: boolean;
  isLoadingItems?: boolean;
  /** When provided, item filtering is delegated to the server. */
  onSearchItems?: (q: string) => void;
  composeMode?: ComposeMode;
  onInsert: (text: string) => void;
  extraActions?: React.ReactNode;
}) {
  const [groupFilter, setGroupFilter] = useState("");
  const [itemQuery, setItemQuery] = useState("");
  const [staged, setStaged] = useState<
    { key: string; text: string; group?: string; values: Record<string, string> }[]
  >([]);

  // Reset per-open so a previous section's staging never leaks into this one.
  useEffect(() => {
    if (!open) {
      setStaged([]);
      setItemQuery("");
      setGroupFilter("");
    }
  }, [open]);

  useEffect(() => {
    if (onSearchItems) onSearchItems(itemQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemQuery]);

  const visibleGroups = useMemo(() => {
    const q = groupFilter.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter((g) => g.label.toLowerCase().includes(q) || g.sublabel?.toLowerCase().includes(q));
  }, [groups, groupFilter]);

  const activeGroup = groups.find((g) => g.id === activeGroupId) ?? null;
  const items = activeGroup?.items ?? [];

  // Client-side filter only when the adapter is not doing it server-side.
  const visibleItems = useMemo(() => {
    if (onSearchItems) return items;
    const q = itemQuery.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => i.text.toLowerCase().includes(q));
  }, [items, itemQuery, onSearchItems]);

  const stagedKeys = new Set(staged.map((s) => s.key));

  const toggleItem = (item: PhraseItem) => {
    const key = `${activeGroup?.id}:${item.id}`;
    if (stagedKeys.has(key)) {
      setStaged((s) => s.filter((x) => x.key !== key));
      return;
    }
    setStaged((s) => [
      ...s,
      {
        key,
        text: item.text,
        group: item.group ?? activeGroup?.label,
        values: defaultValuesFor(parsePhraseTemplate(item.text)),
      },
    ]);
  };

  const composed = useMemo(() => {
    if (!staged.length) return "";
    if (composeMode === "lines") {
      return staged.map((s) => renderStaged(s.text, s.values)).join("\n");
    }
    // grouped: one line per group, findings comma-joined
    const byGroup = new Map<string, string[]>();
    for (const s of staged) {
      const g = s.group ?? "";
      byGroup.set(g, [...(byGroup.get(g) ?? []), renderStaged(s.text, s.values)]);
    }
    return Array.from(byGroup.entries())
      .map(([g, texts]) => (g ? `${g}: ${texts.join(", ")}.` : texts.join(", ")))
      .join("\n");
  }, [staged, composeMode]);

  const insert = () => {
    if (composed.trim()) onInsert(composed);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,240px)_minmax(0,1fr)] gap-3">
          {/* Groups */}
          <div className="flex min-h-0 flex-col rounded-md border">
            <div className="border-b p-1.5">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={groupFilter}
                  onChange={(e) => setGroupFilter(e.target.value)}
                  placeholder="Find template…"
                  className="h-7 pl-7 text-xs"
                />
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              {isLoadingGroups ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : visibleGroups.length === 0 ? (
                <p className="p-3 text-xs italic text-muted-foreground">No templates found.</p>
              ) : (
                <div className="p-1">
                  {visibleGroups.map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      onClick={() => onActiveGroupChange(g.id)}
                      className={cn(
                        "flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-xs transition-colors",
                        g.id === activeGroupId ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">{g.label}</span>
                      {g.tag && (
                        <Badge
                          variant="outline"
                          className={cn(
                            "shrink-0 text-xs",
                            g.id === activeGroupId && "border-primary-foreground/40 text-primary-foreground",
                          )}
                        >
                          {g.tag}
                        </Badge>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>

          {/* Phrases */}
          <div className="flex min-h-0 flex-col rounded-md border">
            <div className="border-b p-1.5">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={itemQuery}
                  onChange={(e) => setItemQuery(e.target.value)}
                  placeholder={activeGroup ? `Search in ${activeGroup.label}…` : "Select a template first"}
                  disabled={!activeGroup}
                  className="h-7 pl-7 text-xs"
                />
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              {!activeGroup ? (
                <p className="p-3 text-xs italic text-muted-foreground">
                  Choose a template on the left to see its phrases.
                </p>
              ) : isLoadingItems ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : visibleItems.length === 0 ? (
                <p className="p-3 text-xs italic text-muted-foreground">
                  {itemQuery ? "No phrases match that search." : "This template has no phrases for this section."}
                </p>
              ) : (
                <div className="space-y-0.5 p-1">
                  {visibleItems.map((item) => {
                    const key = `${activeGroup.id}:${item.id}`;
                    const blanks = countPlaceholders(parsePhraseTemplate(item.text));
                    return (
                      <label
                        key={item.id}
                        className="flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-xs hover:bg-muted"
                      >
                        <Checkbox
                          checked={stagedKeys.has(key)}
                          onCheckedChange={() => toggleItem(item)}
                          className="mt-0.5"
                        />
                        <span className="min-w-0 flex-1 whitespace-pre-wrap">{item.text}</span>
                        {blanks > 0 && (
                          <Badge variant="outline" className="shrink-0 border-amber-500/40 text-xs text-amber-600">
                            {blanks} to fill
                          </Badge>
                        )}
                      </label>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </div>
        </div>

        {/* Staged tray — where the template becomes patient-specific */}
        {staged.length > 0 && (
          <div className="shrink-0 space-y-1.5 rounded-md border bg-muted/20 p-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Selected ({staged.length})
              </span>
              <Button variant="ghost" size="sm" className="h-5 px-1.5 text-xs" onClick={() => setStaged([])}>
                Clear
              </Button>
            </div>
            <ScrollArea className="max-h-32">
              <div className="space-y-1 pr-2">
                {staged.map((s) => (
                  <PhraseFillRow
                    key={s.key}
                    text={s.text}
                    values={s.values}
                    onChange={(values) =>
                      setStaged((prev) => prev.map((x) => (x.key === s.key ? { ...x, values } : x)))
                    }
                    onRemove={() => setStaged((prev) => prev.filter((x) => x.key !== s.key))}
                  />
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        <DialogFooter className="shrink-0 gap-2 sm:justify-between">
          <div className="flex items-center gap-2">{extraActions}</div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={insert} disabled={!staged.length}>
              Insert {staged.length > 0 && `(${staged.length})`}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
