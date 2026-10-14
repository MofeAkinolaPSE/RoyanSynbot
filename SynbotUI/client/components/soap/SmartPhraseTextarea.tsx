import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Zap } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { parsePhraseTemplate, renderPhrase, defaultValuesFor } from "@/lib/phrase-template";

/**
 * Textarea with inline dot-phrase expansion.
 *
 * Type a trigger (e.g. "NEXANKLES") and pick from the popover; the trigger is
 * replaced in place by the expansion, with any {token:id::default} placeholders
 * resolved to their defaults. 1,209 smart phrases came across from Hope.
 *
 * This is a Textarea DECORATOR, not a picker dialog — a trigger typed at the
 * caret is a fundamentally different interaction from browsing a template, and
 * forcing both into one component would have meant a dialog carrying two
 * mutually exclusive models.
 *
 * Placeholders resolve to their template defaults on insert rather than opening
 * a fill UI: the point of a dot phrase is speed. The full fill experience lives
 * in the template pickers, which is the deliberate path when you want to tune
 * each blank.
 */
export function SmartPhraseTextarea({
  value,
  onChange,
  isNursing,
  className,
  ...props
}: {
  value: string;
  onChange: (v: string) => void;
  isNursing?: boolean;
} & Omit<React.ComponentProps<typeof Textarea>, "value" | "onChange">) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [token, setToken] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const { data, isFetching } = useQuery({
    queryKey: ["smart-phrase-inline", token, !!isNursing],
    queryFn: () => api.hospital.clinical.searchSmartPhrases(token, isNursing),
    enabled: open && token.length >= 3,
    staleTime: 300_000,
  });
  const matches: any[] = (data?.phrases ?? []).slice(0, 6);

  useEffect(() => setHighlight(0), [token]);

  /** The word immediately before the caret, if it looks like a trigger. */
  const currentToken = (el: HTMLTextAreaElement): { word: string; start: number } | null => {
    const caret = el.selectionStart ?? 0;
    const before = el.value.slice(0, caret);
    const m = before.match(/([A-Za-z][A-Za-z0-9._-]{2,})$/);
    if (!m) return null;
    return { word: m[1], start: caret - m[1].length };
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
    const t = currentToken(e.target);
    if (t) {
      setToken(t.word);
      setOpen(true);
    } else {
      setOpen(false);
      setToken("");
    }
  };

  const insert = (phrase: any) => {
    const el = ref.current;
    if (!el) return;
    const t = currentToken(el);
    if (!t) return;

    const tokens = parsePhraseTemplate(phrase.phrase_text);
    const expanded = renderPhrase(tokens, defaultValuesFor(tokens));

    const caret = el.selectionStart ?? 0;
    const next = value.slice(0, t.start) + expanded + value.slice(caret);
    onChange(next);
    setOpen(false);
    setToken("");

    // Put the caret after the inserted text rather than leaving it where the
    // trigger used to be.
    requestAnimationFrame(() => {
      const pos = t.start + expanded.length;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!open || matches.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % matches.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h - 1 + matches.length) % matches.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      // Only intercept Enter when a suggestion is actually highlighted —
      // otherwise a clinician pressing Enter for a new line would get an
      // expansion they never asked for.
      e.preventDefault();
      insert(matches[highlight]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className={cn("relative", className)}>
      <Textarea
        {...props}
        ref={ref}
        value={value}
        onChange={handleChange}
        onKeyDown={onKeyDown}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />

      {open && token.length >= 3 && (isFetching || matches.length > 0) && (
        <div className="absolute left-2 right-2 top-full z-50 mt-1 rounded-md border bg-popover shadow-md">
          <div className="flex items-center gap-1 border-b px-2 py-1 text-xs uppercase tracking-wide text-muted-foreground">
            <Zap className="h-3 w-3" /> Smart phrase
          </div>
          {isFetching ? (
            <div className="flex items-center justify-center py-3">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <ScrollArea className="max-h-40">
              {matches.map((p, i) => (
                <button
                  key={p.id}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insert(p)}
                  onMouseEnter={() => setHighlight(i)}
                  className={cn(
                    "flex w-full flex-col items-start gap-0.5 px-2 py-1.5 text-left text-xs",
                    i === highlight ? "bg-accent" : "hover:bg-muted",
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    <Badge variant="outline" className="font-mono text-xs">{p.phrase}</Badge>
                    {p.is_nursing && <span className="text-xs text-muted-foreground">nursing</span>}
                  </span>
                  <span className="line-clamp-2 text-xs text-muted-foreground">
                    {(p.phrase_text ?? "").replace(/\\r\\n|\\n/g, " ").slice(0, 110)}
                  </span>
                </button>
              ))}
            </ScrollArea>
          )}
        </div>
      )}
    </div>
  );
}
