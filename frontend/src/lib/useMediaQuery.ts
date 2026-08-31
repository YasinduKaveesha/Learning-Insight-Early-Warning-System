import { useEffect, useState } from "react";

/** Plan §8's ≥1024px breakpoint, where the watch-list master-detail layout
 * (hardening-pass gap 2) applies. Used to pick the SAME watch card's link
 * target — the detail route inline at ≥1024, or the standalone
 * `/students/:id` route below it — never to change what data loads or how
 * the URL is otherwise structured. */
export const IS_DESKTOP_QUERY = "(min-width: 1024px)";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const listener = () => setMatches(mql.matches);
    listener();
    mql.addEventListener("change", listener);
    return () => mql.removeEventListener("change", listener);
  }, [query]);

  return matches;
}
