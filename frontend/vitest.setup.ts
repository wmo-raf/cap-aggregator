import { vi } from "vitest";

// maplibre-gl creates a worker blob URL at import time; jsdom has no
// createObjectURL. The map itself is never instantiated in unit tests.
if (typeof window !== "undefined" && !window.URL.createObjectURL) {
  window.URL.createObjectURL = vi.fn(() => "blob:vitest-stub");
}
