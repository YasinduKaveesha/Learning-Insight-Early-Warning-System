import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine, so window.matchMedia isn't implemented at all
// (calling it throws). Default every query to "not matched" (mobile-first,
// matching plan §8's default) so useMediaQuery-based components don't crash
// under test; a test exercising the >=1024px master-detail layout overrides
// window.matchMedia for that one test only (see WatchListScreen.test.tsx).
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}
