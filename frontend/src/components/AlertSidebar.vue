<script setup lang="ts">
import { ChevronDown } from "lucide-vue-next";

import ExplorerSidebar from "@/components/ExplorerSidebar.vue";
import FilterPanel from "@/components/FilterPanel.vue";
import type { AlertListItem } from "@/lib/api";
import type { AlertFilters } from "@/lib/filters";
import { groupBySeverity } from "@/lib/grouping";

defineProps<{
  alerts: AlertListItem[];
  total: number;
  state: "loading" | "ready" | "error";
  filters: AlertFilters;
  countries: { code: string; name: string }[];
}>();
const emit = defineEmits<{ "update:filters": [filters: AlertFilters] }>();

function expiryLabel(expires: string | null): string {
  if (!expires) return "";
  return `until ${new Date(expires).toLocaleString()}`;
}
</script>

<template>
  <ExplorerSidebar title="Map" description="Filter and browse alerts in the current view.">
    <FilterPanel
      class="shrink-0"
      :model-value="filters"
      :countries="countries"
      @update:model-value="emit('update:filters', $event)"
    />

    <section class="sidebar-panel flex min-h-0 flex-col" aria-label="Alert list">
      <header class="sidebar-panel__header shrink-0">
        <h3>Alerts in view</h3>
        <span class="text-xs text-muted-foreground" data-testid="alert-total">{{ total }}</span>
      </header>

      <div class="min-h-0 overflow-y-auto p-2">
        <p v-if="state === 'loading'" class="px-1 text-sm text-muted-foreground">Loading…</p>
        <p v-else-if="state === 'error'" class="px-1 text-sm text-destructive" role="alert">
          Could not load alerts for this view.
        </p>
        <p v-else-if="!alerts.length" class="px-1 text-sm text-muted-foreground">
          No active alerts in the current view.
        </p>

        <div v-else class="flex flex-col gap-2">
          <details
            v-for="group in groupBySeverity(alerts)"
            :key="group.value"
            open
            class="group/sev rounded-md border border-border/70"
          >
            <summary
              class="flex cursor-pointer items-center justify-between gap-2 px-2.5 py-1.5 text-sm font-medium select-none [&::-webkit-details-marker]:hidden"
              :data-severity-group="group.value"
            >
              <span class="flex items-center gap-2">
                <span class="inline-block size-2.5 rounded-full" :style="{ backgroundColor: group.color }" aria-hidden="true"></span>
                {{ group.label }}
                <span class="text-xs font-normal text-muted-foreground">{{ group.items.length }}</span>
              </span>
              <ChevronDown class="size-4 text-muted-foreground transition-transform group-open/sev:rotate-180" aria-hidden="true" />
            </summary>
            <ul class="flex flex-col gap-1.5 px-2 pt-0.5 pb-2">
              <li v-for="alert in group.items" :key="alert.id">
                <a
                  :href="`/alerts/${alert.chain}/`"
                  class="flex flex-col gap-0.5 rounded-md border border-border bg-background p-2.5 transition-colors hover:bg-accent"
                >
                  <span class="truncate text-sm font-medium">{{ alert.headline || alert.event }}</span>
                  <span class="text-xs text-muted-foreground">{{ alert.event }} · {{ alert.authority }}</span>
                  <span v-if="alert.expires" class="text-xs text-muted-foreground">{{ expiryLabel(alert.expires) }}</span>
                </a>
              </li>
            </ul>
          </details>
        </div>
      </div>
    </section>
  </ExplorerSidebar>
</template>
