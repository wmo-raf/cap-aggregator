<script setup lang="ts">
import { Bell, Landmark, Map as MapIcon, Moon, Sun, Table2 } from "lucide-vue-next";
import { RouterLink, useRoute } from "vue-router";

import { useSidebar } from "@/composables/useSidebar";
import { useTheme } from "@/composables/useTheme";

const { isDark, toggle } = useTheme();
const route = useRoute();
const sidebar = useSidebar();

const items = [
  { name: "map", label: "Map", icon: MapIcon, hasSidebar: true },
  { name: "table", label: "Table", icon: Table2, hasSidebar: true },
  { name: "authorities", label: "Authorities", icon: Landmark, hasSidebar: true },
  { name: "notify", label: "Notify", icon: Bell, hasSidebar: false },
];

/** Clicking the item of the view you're on toggles its sidebar instead of
 * (re)navigating; other items navigate with the shared state carried over. */
function onItemClick(item: (typeof items)[number], event: MouseEvent) {
  if (route.name === item.name && item.hasSidebar) {
    event.preventDefault();
    sidebar.toggle();
  }
}

const logoUrl = "/static/images/cap-agg-logo.png";
</script>

<template>
  <nav
    class="fixed inset-x-0 bottom-0 z-20 flex h-16 shrink-0 items-stretch justify-around border-t border-border bg-card md:static md:inset-auto md:h-auto md:w-20 md:flex-col md:justify-start md:gap-1 md:border-r md:border-t-0 md:px-2 md:py-3"
    aria-label="Explorer navigation"
  >
    <a
      href="/"
      class="flex items-center justify-center rounded-md px-2 md:mb-4 md:p-2"
      title="CAP Aggregator home"
    >
      <img :src="logoUrl" alt="CAP Aggregator" class="h-8 w-auto md:h-10" />
    </a>

    <RouterLink
      v-for="item in items"
      :key="item.name"
      :to="{ name: item.name }"
      class="flex flex-1 flex-col items-center justify-center gap-1 rounded-md py-2 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground md:flex-none"
      active-class="bg-accent text-foreground"
      @click="onItemClick(item, $event)"
    >
      <component :is="item.icon" class="size-5" aria-hidden="true" />
      <span>{{ item.label }}</span>
    </RouterLink>

    <button
      type="button"
      class="flex flex-1 flex-col items-center justify-center gap-1 rounded-md py-2 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground md:mt-auto md:flex-none"
      :aria-pressed="isDark"
      data-testid="theme-toggle"
      @click="toggle"
    >
      <Sun v-if="isDark" class="size-5" aria-hidden="true" />
      <Moon v-else class="size-5" aria-hidden="true" />
      <span>{{ isDark ? "Light" : "Dark" }}</span>
    </button>
  </nav>
</template>
