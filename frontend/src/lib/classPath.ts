/** Which class a URL is about -- /classes/:id and its /watch, /requests and
 * /reports screens alike. Null on every screen that belongs to no one class.
 *
 * Lives here rather than beside the component that uses it so that file only
 * exports components (fast refresh), and so the rule can be tested on its own.
 */
export function classIdFromPath(pathname: string): string | null {
  return /^\/classes\/([^/]+)/.exec(pathname)?.[1] ?? null;
}
