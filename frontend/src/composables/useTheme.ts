import { readonly, ref } from "vue";

const STORAGE_KEY = "capagg-theme";

// Module-level singleton: every component sees the same theme state.
const isDark = ref(document.documentElement.classList.contains("dark"));

function apply(dark: boolean) {
  isDark.value = dark;
  document.documentElement.classList.toggle("dark", dark);
  localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
}

/**
 * App-wide dark mode. The shell template applies the stored theme to <html>
 * before first paint (to avoid a flash); this composable owns it afterwards.
 */
export function useTheme() {
  return {
    isDark: readonly(isDark),
    toggle: () => apply(!isDark.value),
    set: apply,
  };
}

export function initTheme() {
  const stored = localStorage.getItem(STORAGE_KEY);
  const dark =
    stored === "dark" ||
    (stored === null && window.matchMedia("(prefers-color-scheme: dark)").matches);
  apply(dark);
}
