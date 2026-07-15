<script setup lang="ts">
import { PanelLeftClose, PanelLeftOpen } from "lucide-vue-next";
import { computed, ref } from "vue";

/**
 * Shared collapsible sidebar shell for the explorer views.
 * - "overlay": floats over the content full-height (map) with a slide.
 * - "inline": an in-flow column (table/authorities); collapsing animates the
 *   width closed so the content beside it reclaims the space.
 * Session-only state: every navigation starts open.
 */
const props = withDefaults(
  defineProps<{ variant?: "overlay" | "inline"; label?: string }>(),
  { variant: "inline", label: "Sidebar" },
);

const open = ref(true);

const transitionClasses = computed(() =>
  props.variant === "overlay"
    ? {
        enterActive: "transition-transform duration-200 ease-out",
        enterFrom: "-translate-x-full",
        enterTo: "",
        leaveActive: "transition-transform duration-200 ease-in",
        leaveTo: "-translate-x-full",
        leaveFrom: "",
      }
    : {
        enterActive: "transition-all duration-200 ease-out overflow-hidden",
        enterFrom: "max-w-0 opacity-0",
        enterTo: "max-w-96 opacity-100",
        leaveActive: "transition-all duration-200 ease-in overflow-hidden",
        leaveFrom: "max-w-96 opacity-100",
        leaveTo: "max-w-0 opacity-0",
      },
);
</script>

<template>
  <div
    :class="
      variant === 'overlay'
        ? 'pointer-events-auto flex h-full items-start'
        : 'flex w-full items-start gap-2 lg:w-auto'
    "
  >
    <Transition
      :enter-active-class="transitionClasses.enterActive"
      :enter-from-class="transitionClasses.enterFrom"
      :enter-to-class="transitionClasses.enterTo"
      :leave-active-class="transitionClasses.leaveActive"
      :leave-from-class="transitionClasses.leaveFrom"
      :leave-to-class="transitionClasses.leaveTo"
    >
      <aside
        v-if="open"
        :aria-label="label"
        :class="
          variant === 'overlay'
            ? 'flex h-full w-72 flex-col gap-3 overflow-y-auto border-r border-border bg-card/95 p-3 backdrop-blur sm:w-80'
            : 'flex min-w-0 flex-1 flex-col gap-3 lg:w-64 lg:flex-none'
        "
      >
        <slot />
      </aside>
    </Transition>

    <button
      type="button"
      class="rounded-md border border-border bg-card/90 p-2 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:text-foreground"
      :class="variant === 'overlay' ? 'm-2' : 'shrink-0'"
      :aria-expanded="open"
      :title="open ? 'Collapse sidebar' : 'Show sidebar'"
      data-testid="sidebar-toggle"
      @click="open = !open"
    >
      <PanelLeftClose v-if="open" class="size-4" aria-hidden="true" />
      <PanelLeftOpen v-else class="size-4" aria-hidden="true" />
    </button>
  </div>
</template>
