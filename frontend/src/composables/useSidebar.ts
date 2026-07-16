import { type Ref, readonly, ref } from "vue";

/**
 * Per-view open state for the docked explorer sidebar (session-only).
 * Menu semantics: clicking a view's menu item while elsewhere navigates AND
 * opens that view's sidebar ("first click always opens"); clicking the
 * active view's item toggles it. Closing on one view never affects another.
 * First visit defaults: open on desktop, closed on small screens.
 */
/** Push-transition duration — keep in sync with the duration-200 classes in
 * ExplorerSidebar.vue. Views with resize-sensitive content (the map) settle
 * once after this instead of tracking the animation frame-by-frame. */
export const SIDEBAR_TRANSITION_MS = 200;

function defaultOpen(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(min-width: 768px)").matches;
}

const states = new Map<string, Ref<boolean>>();

function stateFor(view: string): Ref<boolean> {
  let state = states.get(view);
  if (!state) {
    state = ref(defaultOpen());
    states.set(view, state);
  }
  return state;
}

export function useSidebar() {
  return {
    isOpen: (view: string) => readonly(stateFor(view)),
    toggle: (view: string) => {
      stateFor(view).value = !stateFor(view).value;
    },
    open: (view: string) => {
      stateFor(view).value = true;
    },
    close: (view: string) => {
      stateFor(view).value = false;
    },
  };
}
