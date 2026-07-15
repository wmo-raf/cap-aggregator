import { readonly, ref } from "vue";

/**
 * Shared open state for the docked explorer sidebar (one state for all
 * views — session-only). Toggled by clicking the active main-menu item;
 * closed by the sidebar's own close button. Defaults open on desktop,
 * closed on small screens.
 */
function defaultOpen(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(min-width: 768px)").matches;
}

const open = ref(defaultOpen());

export function useSidebar() {
  return {
    open: readonly(open),
    toggle: () => {
      open.value = !open.value;
    },
    openSidebar: () => {
      open.value = true;
    },
    close: () => {
      open.value = false;
    },
  };
}
