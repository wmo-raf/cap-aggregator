import { beforeEach, describe, expect, it } from "vitest";

import { useSidebar } from "@/composables/useSidebar";

describe("per-view sidebar state", () => {
  beforeEach(() => {
    const sidebar = useSidebar();
    for (const view of ["map", "table", "authorities"]) sidebar.open(view);
  });

  it("keeps each view's state independent", () => {
    const sidebar = useSidebar();

    sidebar.close("map");

    expect(sidebar.isOpen("map").value).toBe(false);
    expect(sidebar.isOpen("table").value).toBe(true);
    expect(sidebar.isOpen("authorities").value).toBe(true);
  });

  it("toggles a single view", () => {
    const sidebar = useSidebar();

    sidebar.toggle("table");
    expect(sidebar.isOpen("table").value).toBe(false);
    sidebar.toggle("table");
    expect(sidebar.isOpen("table").value).toBe(true);
  });
});
