<script setup lang="ts">
import { PanelLeftClose, PanelLeftOpen } from "lucide-vue-next";
import { ref } from "vue";

import FilterPanel from "@/components/FilterPanel.vue";
import type { AlertListItem } from "@/lib/api";
import type { AlertFilters } from "@/lib/filters";
import { SEVERITIES, SEVERITY_FALLBACK_COLOR } from "@/lib/severity";

defineProps<{
  alerts: AlertListItem[];
  total: number;
  state: "loading" | "ready" | "error";
  filters: AlertFilters;
  countries: { code: string; name: string }[];
}>();
const emit = defineEmits<{ "update:filters": [filters: AlertFilters] }>();

const open = ref(true);

function severityColor(severity: string): string {
  return SEVERITIES.find((s) => s.value === severity.toLowerCase())?.color ?? SEVERITY_FALLBACK_COLOR;
}

function expiryLabel(expires: string | null): string {
  if (!expires) return "";
  return `until ${new Date(expires).toLocaleString()}`;
}
</script>

<template>
  <div class="pointer-events-auto flex h-full items-start">
    <aside
      v-if="open"
      class="flex h-full w-72 flex-col gap-3 overflow-hidden border-r border-border bg-card/95 p-3 backdrop-blur sm:w-80"
      aria-label="Alerts in view"
    >
      <FilterPanel
        :model-value="filters"
        :countries="countries"
        @update:model-value="emit('update:filters', $event)"
      />

      <div class="flex items-baseline justify-between">
        <h3 class="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Alerts in view</h3>
        <span class="text-xs text-muted-foreground" data-testid="alert-total">{{ total }}</span>
      </div>

      <p v-if="state === 'loading'" class="text-sm text-muted-foreground">Loading…</p>
      <p v-else-if="state === 'error'" class="text-sm text-destructive" role="alert">
        Could not load alerts for this view.
      </p>
      <p v-else-if="!alerts.length" class="text-sm text-muted-foreground">
        No active alerts in the current view.
      </p>

      <ul v-else class="-mr-1 flex flex-1 flex-col gap-2 overflow-y-auto pr-1">
        <li v-for="alert in alerts" :key="alert.id">
          <a
            :href="`/alerts/${alert.chain}/`"
            class="flex flex-col gap-0.5 rounded-md border border-border bg-background p-2.5 transition-colors hover:bg-accent"
          >
            <span class="flex items-center gap-2 text-sm font-medium">
              <span
                class="inline-block size-2.5 shrink-0 rounded-full"
                :style="{ backgroundColor: severityColor(alert.severity) }"
                :title="alert.severity"
                aria-hidden="true"
              ></span>
              <span class="truncate">{{ alert.headline || alert.event }}</span>
            </span>
            <span class="pl-4.5 text-xs text-muted-foreground">
              {{ alert.event }} · {{ alert.authority }}
            </span>
            <span v-if="alert.expires" class="pl-4.5 text-xs text-muted-foreground">
              {{ expiryLabel(alert.expires) }}
            </span>
          </a>
        </li>
      </ul>
    </aside>

    <button
      type="button"
      class="m-2 rounded-md border border-border bg-card/90 p-2 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:text-foreground"
      :aria-expanded="open"
      :title="open ? 'Collapse alert list' : 'Show alert list'"
      data-testid="sidebar-toggle"
      @click="open = !open"
    >
      <PanelLeftClose v-if="open" class="size-4" aria-hidden="true" />
      <PanelLeftOpen v-else class="size-4" aria-hidden="true" />
    </button>
  </div>
</template>
