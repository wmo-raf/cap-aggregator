<script setup lang="ts">
import { ChevronDown, ChevronLeft, ChevronRight, Table2 } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import ExplorerSidebar from "@/components/ExplorerSidebar.vue";
import FilterPanel from "@/components/FilterPanel.vue";
import { fetchAlertTable, fetchAuthorities, type TableAlert } from "@/lib/api";
import { type DateRange, rangeFromQuery, rangeToQuery, TABLE_PAGE_SIZE } from "@/lib/dateRange";
import {
  type AlertFilters,
  FACET_PARAMS,
  filtersFromRouteQuery,
  filtersToRouteQuery,
} from "@/lib/filters";
import { groupBySeverity } from "@/lib/grouping";

const route = useRoute();
const router = useRouter();

const filters = ref<AlertFilters>(filtersFromRouteQuery(route.query));
const range = ref<DateRange>(rangeFromQuery(route.query as Record<string, unknown>));
const offset = ref(0);

const alerts = ref<TableAlert[]>([]);
const total = ref(0);
const state = ref<"loading" | "ready" | "error">("loading");
const countries = ref<{ code: string; name: string }[]>([]);

const groups = computed(() => groupBySeverity(alerts.value));
const collapsed = ref(new Set<string>());

function toggleGroup(value: string) {
  const next = new Set(collapsed.value);
  if (!next.delete(value)) next.add(value);
  collapsed.value = next;
}

const pageStart = computed(() => Math.min(offset.value + 1, total.value));
const pageEnd = computed(() => Math.min(offset.value + TABLE_PAGE_SIZE, total.value));

async function load() {
  state.value = "loading";
  try {
    const page = await fetchAlertTable(filters.value, range.value, offset.value);
    alerts.value = page.alerts;
    total.value = page.total;
    state.value = "ready";
  } catch {
    state.value = "error";
  }
}

function syncUrl() {
  const query = { ...route.query };
  for (const param of [...FACET_PARAMS, "from", "to"]) delete query[param];
  router.replace({ query: { ...query, ...filtersToRouteQuery(filters.value), ...rangeToQuery(range.value) } });
}

watch([filters, range], () => {
  offset.value = 0;
  syncUrl();
  load();
}, { deep: true });

watch(offset, load);

function fmt(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

onMounted(async () => {
  load();
  try {
    const seen = new Set<string>();
    countries.value = (await fetchAuthorities())
      .filter((a) => a.country && !seen.has(a.country) && seen.add(a.country))
      .map((a) => ({ code: a.country, name: a.country_name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  } catch {
    countries.value = [];
  }
});
</script>

<template>
  <section class="flex h-full flex-col gap-4 overflow-auto p-4 md:p-6">
    <header class="flex flex-col gap-1">
      <h1 class="flex items-center gap-2 text-xl font-semibold">
        <Table2 class="size-5 text-muted-foreground" aria-hidden="true" />
        Alert archive
      </h1>
      <p class="text-sm text-muted-foreground">Alerts issued within the selected date range.</p>
    </header>

    <div class="flex flex-col gap-4 lg:flex-row">
      <ExplorerSidebar label="Table filters">
        <section class="sidebar-panel" aria-label="Date range">
          <header class="sidebar-panel__header">
            <h3>Date range</h3>
          </header>
          <div class="flex flex-col gap-2 p-3">
            <label class="flex flex-col text-xs text-muted-foreground">
              From
              <input
                type="date"
                class="mt-0.5 rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
                :value="range.from"
                data-testid="range-from"
                @change="range = { ...range, from: ($event.target as HTMLInputElement).value }"
              />
            </label>
            <label class="flex flex-col text-xs text-muted-foreground">
              To
              <input
                type="date"
                class="mt-0.5 rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
                :value="range.to"
                data-testid="range-to"
                @change="range = { ...range, to: ($event.target as HTMLInputElement).value }"
              />
            </label>
          </div>
        </section>

        <FilterPanel v-model="filters" :countries="countries" />
      </ExplorerSidebar>

      <div class="min-w-0 flex-1">
        <p v-if="state === 'loading'" class="text-sm text-muted-foreground">Loading alerts…</p>
        <p v-else-if="state === 'error'" class="text-sm text-destructive" role="alert">
          Could not load alerts. Please try again later.
        </p>
        <p v-else-if="!alerts.length" class="text-sm text-muted-foreground">
          No alerts were issued in this period.
        </p>

        <div v-else class="overflow-x-auto rounded-lg border border-border">
          <table class="w-full min-w-[44rem] text-sm">
            <thead>
              <tr class="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th class="px-3 py-2 font-medium">Event</th>
                <th class="px-3 py-2 font-medium">Severity</th>
                <th class="px-3 py-2 font-medium">Authority</th>
                <th class="px-3 py-2 font-medium">Countries</th>
                <th class="px-3 py-2 font-medium">Effective</th>
                <th class="px-3 py-2 font-medium">Expires</th>
                <th class="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="group in groups" :key="group.value">
                <tr class="border-b border-border bg-muted/25">
                  <td colspan="7" class="px-3 py-1.5">
                    <button
                      type="button"
                      class="flex w-full items-center justify-between gap-2 text-left text-sm font-semibold"
                      :aria-expanded="!collapsed.has(group.value)"
                      :data-severity-group="group.value"
                      @click="toggleGroup(group.value)"
                    >
                      <span class="flex items-center gap-2">
                        <span class="inline-block size-2.5 rounded-full" :style="{ backgroundColor: group.color }" aria-hidden="true"></span>
                        {{ group.label }}
                        <span class="text-xs font-normal text-muted-foreground">{{ group.items.length }}</span>
                      </span>
                      <ChevronDown
                        class="size-4 text-muted-foreground transition-transform"
                        :class="collapsed.has(group.value) ? '-rotate-90' : ''"
                        aria-hidden="true"
                      />
                    </button>
                  </td>
                </tr>
                <template v-if="!collapsed.has(group.value)">
                  <tr
                    v-for="alert in group.items"
                    :key="alert.id"
                    class="cursor-pointer border-b border-border transition-colors last:border-b-0 hover:bg-accent"
                  >
                    <td class="px-3 py-2">
                      <a :href="`/alerts/${alert.chain}/`" class="flex items-center gap-2 font-medium">
                        <span
                          class="inline-block size-2.5 shrink-0 rounded-full"
                          :style="{ backgroundColor: group.color }"
                          aria-hidden="true"
                        ></span>
                        <span class="max-w-64 truncate">{{ alert.headline || alert.event }}</span>
                      </a>
                    </td>
                    <td class="px-3 py-2">{{ alert.severity }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ alert.authority }}</td>
                    <td class="px-3 py-2 uppercase text-muted-foreground">{{ alert.countries.join(", ") }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ fmt(alert.effective) }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ fmt(alert.expires) }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ alert.status }}{{ alert.is_cancelled ? " (cancelled)" : "" }}</td>
                  </tr>
                </template>
              </template>
            </tbody>
          </table>
        </div>

        <div v-if="total > TABLE_PAGE_SIZE" class="mt-3 flex items-center justify-between text-sm text-muted-foreground">
          <span data-testid="page-info">{{ pageStart }}–{{ pageEnd }} of {{ total }}</span>
          <div class="flex gap-2">
            <button
              type="button"
              class="flex items-center gap-1 rounded-md border border-border px-2 py-1 transition-colors hover:bg-accent disabled:opacity-40"
              :disabled="offset === 0"
              @click="offset = Math.max(0, offset - TABLE_PAGE_SIZE)"
            >
              <ChevronLeft class="size-4" aria-hidden="true" /> Prev
            </button>
            <button
              type="button"
              class="flex items-center gap-1 rounded-md border border-border px-2 py-1 transition-colors hover:bg-accent disabled:opacity-40"
              :disabled="offset + TABLE_PAGE_SIZE >= total"
              @click="offset = offset + TABLE_PAGE_SIZE"
            >
              Next <ChevronRight class="size-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
