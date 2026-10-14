import { describe, it, expect } from "vitest";
import {
  parsePhraseTemplate,
  renderPhrase,
  renderPhraseText,
  hasPlaceholders,
  countPlaceholders,
  defaultValuesFor,
  choiceTokenIds,
} from "./phrase-template";

describe("parsePhraseTemplate", () => {
  it("returns [] for empty/nullish input", () => {
    expect(parsePhraseTemplate("")).toEqual([]);
    expect(parsePhraseTemplate(null)).toEqual([]);
    expect(parsePhraseTemplate(undefined)).toEqual([]);
  });

  it("treats plain prose as a single literal", () => {
    const t = parsePhraseTemplate("Abdomen soft, non-tender.");
    expect(t).toHaveLength(1);
    expect(t[0]).toEqual({ kind: "literal", text: "Abdomen soft, non-tender." });
  });

  // Real row from royan_note_template_texts
  it("splits a '??' blank out of real template prose", () => {
    const t = parsePhraseTemplate("Squamous cell ca situ of ??");
    expect(t.map((x) => x.kind)).toEqual(["literal", "blank"]);
  });

  // Real row from royan_smart_phrases (NEXANKLES)
  it("parses a {label:tokenId::default} choice", () => {
    const t = parsePhraseTemplate("Ankle exam - {side:15002::both sides} normal");
    expect(t.map((x) => x.kind)).toEqual(["literal", "choice", "literal"]);
    const choice = t[1] as Extract<(typeof t)[number], { kind: "choice" }>;
    expect(choice.label).toBe("side");
    expect(choice.tokenId).toBe("15002");
    expect(choice.defaultValue).toBe("both sides");
  });

  it("handles several blanks and choices in one phrase", () => {
    const t = parsePhraseTemplate("?? and {a:1::x} then ?? plus {b:2::y}");
    expect(countPlaceholders(t)).toBe(4);
    expect(choiceTokenIds(t)).toEqual(["1", "2"]);
  });

  it("gives every placeholder a distinct id", () => {
    const t = parsePhraseTemplate("?? / ?? / ??");
    const ids = t.filter((x) => x.kind !== "literal").map((x: any) => x.id);
    expect(new Set(ids).size).toBe(3);
  });
});

// These are the cases that matter: 8,370 clinician-written rows will contain
// malformed syntax, and a throw inside a note editor is unacceptable.
describe("parsePhraseTemplate — degrades instead of throwing", () => {
  const nasty = [
    "Unbalanced { brace",
    "Closing } only",
    "{missing::default}",          // no tokenId segment
    "{label:token:single}",        // single colon, not double
    "{}",
    "{:::}",
    "Nested {out{in:1::v}er}",
    "Is this normal?? Yes.",       // legitimate prose that contains "??"
    "100%{ok",
  ];

  it.each(nasty)("survives %j", (input) => {
    expect(() => parsePhraseTemplate(input)).not.toThrow();
    const tokens = parsePhraseTemplate(input);
    expect(() => renderPhrase(tokens, {})).not.toThrow();
  });

  it("keeps unrecognised brace syntax as literal text", () => {
    const t = parsePhraseTemplate("{label:token:single}");
    expect(t.every((x) => x.kind === "literal")).toBe(true);
    expect(renderPhrase(t)).toBe("{label:token:single}");
  });

  it("still detects a real '??' inside otherwise prose-like text", () => {
    // "Is this normal?? Yes." — the '??' is punctuation, but we cannot
    // distinguish it from a blank. Documented behaviour: treated as a blank,
    // and an unfilled blank renders as '___' rather than corrupting the note.
    const t = parsePhraseTemplate("Is this normal?? Yes.");
    expect(hasPlaceholders(t)).toBe(true);
    expect(renderPhrase(t)).toBe("Is this normal___ Yes.");
  });
});

describe("renderPhrase", () => {
  it("substitutes a filled blank", () => {
    const t = parsePhraseTemplate("Squamous cell ca situ of ??");
    const id = (t.find((x) => x.kind === "blank") as any).id;
    expect(renderPhrase(t, { [id]: "the left cheek" })).toBe(
      "Squamous cell ca situ of the left cheek",
    );
  });

  // The medico-legal requirement: never leak template syntax into a signed note.
  it("renders an UNFILLED blank as '___', never as '??'", () => {
    const out = renderPhraseText("Lesion noted on ??");
    expect(out).toBe("Lesion noted on ___");
    expect(out).not.toContain("??");
  });

  it("falls back to the choice default when unfilled", () => {
    expect(renderPhraseText("Ankle exam - {side:15002::both sides} normal")).toBe(
      "Ankle exam - both sides normal",
    );
  });

  it("prefers a supplied choice value over the default", () => {
    const t = parsePhraseTemplate("Ankle exam - {side:15002::both sides} normal");
    const id = (t.find((x) => x.kind === "choice") as any).id;
    expect(renderPhrase(t, { [id]: "Left" })).toBe("Ankle exam - Left normal");
  });

  it("treats a whitespace-only value as unfilled", () => {
    const t = parsePhraseTemplate("Site: ??");
    const id = (t.find((x) => x.kind === "blank") as any).id;
    expect(renderPhrase(t, { [id]: "   " })).toBe("Site: ___");
  });

  it("uses '___' when a choice has neither value nor default", () => {
    expect(renderPhraseText("Side: {side:1::}")).toBe("Side: ___");
  });

  it("round-trips prose with no placeholders unchanged", () => {
    const s = "Chest clear, air entry equal bilaterally.";
    expect(renderPhraseText(s)).toBe(s);
  });
});

describe("helpers", () => {
  it("hasPlaceholders distinguishes plain prose from fill-in phrases", () => {
    expect(hasPlaceholders(parsePhraseTemplate("No acute distress."))).toBe(false);
    expect(hasPlaceholders(parsePhraseTemplate("Pain score ??/10"))).toBe(true);
  });

  it("defaultValuesFor seeds choice defaults only", () => {
    const t = parsePhraseTemplate("?? and {side:15002::both sides}");
    const d = defaultValuesFor(t);
    expect(Object.values(d)).toEqual(["both sides"]);
  });

  it("choiceTokenIds de-duplicates repeated tokens", () => {
    const t = parsePhraseTemplate("{a:15002::x} then {b:15002::y}");
    expect(choiceTokenIds(t)).toEqual(["15002"]);
  });
});
