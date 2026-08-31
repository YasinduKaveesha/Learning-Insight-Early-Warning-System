import { FRAMING_LINE } from "../../lib/presentation";

/**
 * Exact required wording (docs/12 §1) in the header of every analytics
 * surface. No paraphrase — the string is imported, never retyped, so a typo
 * can only happen in one place.
 */
export function FramingLine() {
  return <p className="text-sm font-medium text-slate-600">{FRAMING_LINE}</p>;
}
