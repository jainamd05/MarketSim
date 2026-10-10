import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

// jsdom lacks these browser APIs used by Recharts / Radix
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver);
window.scrollTo = window.scrollTo ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => {};
}
