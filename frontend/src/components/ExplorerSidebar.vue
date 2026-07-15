<script setup lang="ts">
import { X } from "lucide-vue-next";
import { computed } from "vue";
import { useRoute } from "vue-router";

import { useSidebar } from "@/composables/useSidebar";

/**
 * The docked explorer sidebar: one full-height column anchored to the main
 * menu rail, identical on every view. Open state is per-view (useSidebar,
 * keyed by route name) and driven by the main menu; the header's close
 * button is the only affordance inside. On small screens it overlays the
 * content instead of docking.
 */
defineProps<{ title: string; description?: string }>();

const route = useRoute();
const sidebar = useSidebar();
const view = computed(() => String(route.name ?? ""));
const open = computed(() => sidebar.isOpen(view.value).value);
const close = () => sidebar.close(view.value);
</script>

<template>
  <Transition
    enter-active-class="transition-all duration-200 ease-out overflow-hidden"
    enter-from-class="max-w-0 opacity-0"
    enter-to-class="max-w-80 opacity-100"
    leave-active-class="transition-all duration-200 ease-in overflow-hidden"
    leave-from-class="max-w-80 opacity-100"
    leave-to-class="max-w-0 opacity-0"
  >
    <aside
      v-if="open"
      :aria-label="title"
      class="absolute inset-y-0 left-0 z-30 flex h-full w-80 max-w-full shrink-0 flex-col border-r border-border bg-card md:static"
    >
      <header class="flex shrink-0 items-start justify-between gap-2 border-b border-border bg-muted px-3 py-2.5">
        <div class="min-w-0">
          <h2 class="text-sm font-semibold">{{ title }}</h2>
          <p v-if="description" class="text-xs text-muted-foreground">{{ description }}</p>
        </div>
        <button
          type="button"
          class="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          title="Close sidebar"
          data-testid="sidebar-close"
          @click="close"
        >
          <X class="size-4" aria-hidden="true" />
        </button>
      </header>

      <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        <slot />
      </div>
    </aside>
  </Transition>
</template>
