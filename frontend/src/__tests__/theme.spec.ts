import { beforeEach, describe, expect, it } from "vitest";

import { initTheme, useTheme } from "@/composables/useTheme";

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("restores a stored dark preference on init", () => {
    localStorage.setItem("capagg-theme", "dark");
    initTheme();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("restores a stored light preference on init", () => {
    localStorage.setItem("capagg-theme", "light");
    initTheme();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("toggle flips the html class and persists the choice", () => {
    localStorage.setItem("capagg-theme", "light");
    initTheme();
    const { isDark, toggle } = useTheme();

    toggle();
    expect(isDark.value).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("capagg-theme")).toBe("dark");

    toggle();
    expect(isDark.value).toBe(false);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("capagg-theme")).toBe("light");
  });
});
