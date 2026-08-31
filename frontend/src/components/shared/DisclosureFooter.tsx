export interface DisclosureFooterProps {
  /** From the API response (HomeSummary.disclosure) — NEVER hard-code this
   * text in a component. The point of serving it from the API is that the
   * required wording cannot drift between screens (plan §4.1). */
  disclosure: string;
}

export function DisclosureFooter({ disclosure }: DisclosureFooterProps) {
  return <p className="px-4 py-3 text-center text-xs text-slate-400">{disclosure}</p>;
}
