import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { parsePhraseTemplate, renderPhrase, type PhraseToken } from "@/lib/phrase-template";

/**
 * One staged phrase, rendered as INLINE RUNS rather than a raw string — this
 * is what "interact with that template based on that particular patient"
 * means concretely.
 *
 *   literal            -> plain text
 *   "??"               -> inline auto-width input with a dashed underline
 *   {side:15002::both} -> inline Select, options fetched by token id,
 *                         pre-selected to the template's own default
 *
 * Nothing here blocks insertion. An unfilled blank serialises to "___" (see
 * lib/phrase-template.ts) so a gap in a signed note reads as deliberate rather
 * than as leaked template syntax.
 */
export function PhraseFillRow({
  text,
  values,
  onChange,
  onRemove,
  className,
}: {
  text: string;
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
  onRemove?: () => void;
  className?: string;
}) {
  const tokens = parsePhraseTemplate(text);

  return (
    <div className={cn("flex items-start gap-1.5 rounded-md border bg-muted/30 px-2 py-1.5", className)}>
      <div className="min-w-0 flex-1 text-xs leading-relaxed">
        {tokens.map((t, i) => (
          <TokenRun
            key={i}
            token={t}
            value={values[(t as any).id]}
            onChange={(v) => onChange({ ...values, [(t as any).id]: v })}
          />
        ))}
      </div>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove phrase"
          className="mt-0.5 shrink-0 text-muted-foreground hover:text-destructive"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

function TokenRun({
  token,
  value,
  onChange,
}: {
  token: PhraseToken;
  value?: string;
  onChange: (v: string) => void;
}) {
  if (token.kind === "literal") return <span className="whitespace-pre-wrap">{token.text}</span>;

  if (token.kind === "blank") {
    return (
      <Input
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder="…"
        className={cn(
          "mx-0.5 inline-flex h-5 w-24 rounded-none border-0 border-b border-dashed border-amber-500/70",
          "bg-transparent px-1 py-0 text-xs focus-visible:ring-0 focus-visible:ring-offset-0",
        )}
      />
    );
  }

  return <ChoiceRun token={token} value={value} onChange={onChange} />;
}

function ChoiceRun({
  token,
  value,
  onChange,
}: {
  token: Extract<PhraseToken, { kind: "choice" }>;
  value?: string;
  onChange: (v: string) => void;
}) {
  // One option list is shared by many phrases, so this is keyed by token id
  // and cached accordingly.
  const { data } = useQuery({
    queryKey: ["smart-phrase-options", token.tokenId],
    queryFn: () => api.hospital.clinical.listSmartPhraseOptions(token.tokenId),
    staleTime: 300_000,
  });
  const options: any[] = data?.options ?? [];
  const current = value ?? token.defaultValue;

  // Until the options land (or if the token has none), the default still
  // renders — the phrase is never blank because a lookup is slow.
  if (!options.length) {
    return <span className="mx-0.5 rounded bg-amber-500/15 px-1 text-amber-700 dark:text-amber-400">{current || "___"}</span>;
  }

  return (
    <Select value={current} onValueChange={onChange}>
      <SelectTrigger
        className="mx-0.5 inline-flex h-5 w-auto gap-1 rounded border-amber-500/40 bg-amber-500/10 px-1.5 py-0 text-xs"
        aria-label={token.label}
      >
        <SelectValue placeholder={token.label} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.id} value={o.option_text} className="text-xs">
            {o.option_text}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Final text for a staged phrase, with whatever the clinician filled in. */
export function renderStaged(text: string, values: Record<string, string>): string {
  return renderPhrase(parsePhraseTemplate(text), values);
}
