/**
 * Phrase template parsing for the SOAP composer.
 *
 * Migrated Hope templates are not text blobs — they are bundles of selectable
 * phrases, and individual phrases carry two kinds of fill-in:
 *
 *   "??"                        a free-text blank
 *   "{side:15002::both sides}"  a choice: label / token id / default value,
 *                               whose options live in royan_smart_phrase_options
 *                               keyed by that token id (15002 = GEN LATERALITY
 *                               -> Right / Left / Bilateral / Both / both sides)
 *
 * This runs against 8,370 phrase rows written by clinicians over ~10 years, so
 * it WILL meet unbalanced braces, stray colons, and legitimate "??" used as
 * real punctuation. Every function here is therefore total: unparseable syntax
 * degrades to literal text rather than throwing. A parser crash inside a
 * clinical note editor is worse than a phrase that renders slightly oddly.
 */

export type PhraseToken =
  | { kind: "literal"; text: string }
  | { kind: "blank"; id: string }
  | { kind: "choice"; id: string; label: string; tokenId: string; defaultValue: string };

/** Matches {label:tokenId::default}. Label and default may contain spaces. */
const CHOICE_RE = /\{([^{}:]+):([^{}:]+)::([^{}]*)\}/g;
const BLANK = "??";

/**
 * Split a phrase into literal / blank / choice runs.
 * Never throws. Unrecognised brace content stays literal.
 */
export function parsePhraseTemplate(text: string | null | undefined): PhraseToken[] {
  if (!text) return [];

  const tokens: PhraseToken[] = [];
  let cursor = 0;
  let seq = 0;

  // Choices first — they may legitimately contain "?" inside their default.
  CHOICE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CHOICE_RE.exec(text)) !== null) {
    if (match.index > cursor) {
      pushLiteralWithBlanks(tokens, text.slice(cursor, match.index), () => `b${seq++}`);
    }
    tokens.push({
      kind: "choice",
      id: `c${seq++}`,
      label: match[1].trim(),
      tokenId: match[2].trim(),
      defaultValue: match[3].trim(),
    });
    cursor = match.index + match[0].length;
  }

  if (cursor < text.length) {
    pushLiteralWithBlanks(tokens, text.slice(cursor), () => `b${seq++}`);
  }
  return tokens;
}

function pushLiteralWithBlanks(out: PhraseToken[], chunk: string, nextId: () => string) {
  let rest = chunk;
  let idx = rest.indexOf(BLANK);
  while (idx !== -1) {
    if (idx > 0) out.push({ kind: "literal", text: rest.slice(0, idx) });
    out.push({ kind: "blank", id: nextId() });
    rest = rest.slice(idx + BLANK.length);
    idx = rest.indexOf(BLANK);
  }
  if (rest) out.push({ kind: "literal", text: rest });
}

/** True when the phrase needs the clinician to fill something in. */
export function hasPlaceholders(tokens: PhraseToken[]): boolean {
  return tokens.some((t) => t.kind !== "literal");
}

export function countPlaceholders(tokens: PhraseToken[]): number {
  return tokens.filter((t) => t.kind !== "literal").length;
}

/**
 * Render tokens back to text using whatever the clinician supplied.
 *
 * An UNFILLED blank becomes "___", never a literal "??". A blank left visible
 * in a signed medico-legal note must read as a deliberate gap, not as leftover
 * template syntax. An unfilled choice falls back to its own default, which is
 * what Hope's own editor did.
 */
export function renderPhrase(
  tokens: PhraseToken[],
  values: Record<string, string> = {},
): string {
  return tokens
    .map((t) => {
      if (t.kind === "literal") return t.text;
      if (t.kind === "blank") {
        const v = (values[t.id] ?? "").trim();
        return v || "___";
      }
      const v = (values[t.id] ?? "").trim();
      return v || t.defaultValue || "___";
    })
    .join("");
}

/** Convenience: parse + render in one step. */
export function renderPhraseText(
  text: string | null | undefined,
  values: Record<string, string> = {},
): string {
  return renderPhrase(parsePhraseTemplate(text), values);
}

/** Seed the value map with each choice's default so nothing renders empty. */
export function defaultValuesFor(tokens: PhraseToken[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const t of tokens) {
    if (t.kind === "choice" && t.defaultValue) out[t.id] = t.defaultValue;
  }
  return out;
}

/** Distinct token ids to fetch option lists for. */
export function choiceTokenIds(tokens: PhraseToken[]): string[] {
  return Array.from(
    new Set(tokens.filter((t): t is Extract<PhraseToken, { kind: "choice" }> => t.kind === "choice").map((t) => t.tokenId)),
  );
}
