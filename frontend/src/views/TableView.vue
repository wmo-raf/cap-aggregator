<script setup lang="ts">
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import ExplorerSidebar from "@/components/ExplorerSidebar.vue";
import FilterPanel from "@/components/FilterPanel.vue";
import { fetchAlertTable, fetchAuthorities, type TableAlert } from "@/lib/api";
import { countryFlagEmoji } from "@/lib/countryFlag";
import { type DateRange, formatDateRange, rangeFromQuery, rangeToQuery, TABLE_PAGE_SIZE } from "@/lib/dateRange";
import {
  type AlertFilters,
  FACET_PARAMS,
  filtersFromRouteQuery,
  filtersToRouteQuery,
} from "@/lib/filters";
import {
  groupByCountryAuthority,
  groupByEffectiveDay,
  groupBySeverity,
  groupingFromQuery,
  groupingToQuery,
  type TableGrouping,
} from "@/lib/grouping";
import { severityColor } from "@/lib/severity";

const route = useRoute();
const router = useRouter();

const filters = ref<AlertFilters>(filtersFromRouteQuery(route.query));
const range = ref<DateRange>(rangeFromQuery(route.query as Record<string, unknown>));
const grouping = ref<TableGrouping>(groupingFromQuery(route.query));
const offset = ref(0);

const alerts = ref<TableAlert[]>([]);
const total = ref(0);
const state = ref<"loading" | "ready" | "error">("loading");
const countries = ref<{ code: string; name: string }[]>([]);

const collapsed = ref(new Set<string>());

function toggleGroup(value: string) {
  const next = new Set(collapsed.value);
  if (!next.delete(value)) next.add(value);
  collapsed.value = next;
}

/** The tbody, flattened: group headers (respecting collapse) then alert rows. */
type DisplayRow =
  | { kind: "header"; key: string; label: string; level: 0 | 1; color?: string }
  | { kind: "alert"; key: string; alert: TableAlert };

const displayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = [];
  const pushAlerts = (items: TableAlert[]) => {
    for (const alert of items) rows.push({ kind: "alert", key: `alert:${alert.id}`, alert });
  };
  const pushFlatGroup = (value: string, label: string, items: TableAlert[], color?: string) => {
    const key = `${grouping.value}:${value}`;
    rows.push({ kind: "header", key, label, level: 0, color });
    if (!collapsed.value.has(key)) pushAlerts(items);
  };

  if (grouping.value === "country") {
    for (const country of groupByCountryAuthority(alerts.value)) {
      const countryKey = `country:${country.code}`;
      const flag = countryFlagEmoji(country.code);
      rows.push({ kind: "header", key: countryKey, label: `${flag} ${country.name}`.trim(), level: 0 });
      if (collapsed.value.has(countryKey)) continue;
      for (const authority of country.authorities) {
        const authorityKey = `authority:${authority.key}`;
        rows.push({ kind: "header", key: authorityKey, label: authority.name, level: 1 });
        if (!collapsed.value.has(authorityKey)) pushAlerts(authority.items);
      }
    }
    return rows;
  }

  if (grouping.value === "severity") {
    for (const group of groupBySeverity(alerts.value)) pushFlatGroup(group.value, group.label, group.items, group.color);
  } else {
    for (const group of groupByEffectiveDay(alerts.value)) pushFlatGroup(group.value, group.label, group.items);
  }
  return rows;
});

const pageStart = computed(() => Math.min(offset.value + 1, total.value));
const pageEnd = computed(() => Math.min(offset.value + TABLE_PAGE_SIZE, total.value));
const appliedRange = computed(() => formatDateRange(range.value));

async function load() {
  state.value = "loading";
  try {
    const page = await fetchAlertTable(filters.value, range.value, offset.value, grouping.value);
    alerts.value = page.alerts;
    total.value = page.total;
    state.value = "ready";
  } catch {
    state.value = "error";
  }
}

function syncUrl() {
  const query = { ...route.query };
  for (const param of [...FACET_PARAMS, "from", "to", "group"]) delete query[param];
  router.replace({
    query: {
      ...query,
      ...filtersToRouteQuery(filters.value),
      ...rangeToQuery(range.value),
      ...groupingToQuery(grouping.value),
    },
  });
}

watch([filters, range], () => {
  offset.value = 0;
  syncUrl();
  load();
}, { deep: true });

watch(grouping, () => {
  offset.value = 0;
  collapsed.value = new Set(); // group keys don't carry across groupings
  syncUrl();
  load();
});

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
  <section class="relative flex h-full w-full">
    <ExplorerSidebar title="Alert archive" description="Alerts issued within the selected date range.">
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

      <div class="flex min-w-0 flex-1 flex-col">
        <header
          class="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-background px-4 py-3 md:px-6"
          data-testid="table-header"
        >
          <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
            <span v-if="state === 'ready'" class="font-semibold" data-testid="table-total">
              {{ total.toLocaleString() }} {{ total === 1 ? "alert" : "alerts" }}
            </span>
            <span v-else-if="state === 'loading'" class="h-4 w-24 animate-pulse rounded bg-muted" aria-hidden="true"></span>
            <span v-if="state !== 'error'" class="text-muted-foreground" aria-hidden="true">·</span>
            <span class="text-muted-foreground" data-testid="table-range">{{ appliedRange }}</span>
          </div>
          <label class="flex items-center gap-2 text-xs text-muted-foreground">
            Group by
            <select
              v-model="grouping"
              class="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
              data-testid="grouping-select"
            >
              <option value="effective">Effective time</option>
              <option value="country">Country &amp; authority</option>
              <option value="severity">Severity</option>
            </select>
          </label>
        </header>

        <p v-if="state === 'error'" class="m-4 text-sm text-destructive md:m-6" role="alert">
          Could not load alerts. Please try again later.
        </p>
        <p v-else-if="state === 'ready' && !alerts.length" class="m-4 text-sm text-muted-foreground md:m-6">
          No alerts were issued in this period.
        </p>

        <div v-else class="flex min-h-0 flex-1 flex-col gap-3 p-4 md:p-6">
          <div class="min-h-0 overflow-auto rounded-lg border border-border">
            <table class="w-full min-w-[44rem] text-sm">
              <thead>
                <tr class="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th
                    v-for="column in ['Event', 'Severity', 'Authority', 'Countries', 'Effective', 'Expires', 'Status']"
                    :key="column"
                    class="sticky top-0 z-10 bg-background px-3 py-2 font-medium shadow-[0_1px_0_0_var(--color-border)]"
                  >
                    {{ column }}
                  </th>
                </tr>
              </thead>
              <tbody v-if="state === 'loading'" data-testid="table-skeleton" aria-busy="true">
                <tr class="border-b border-border bg-muted/25">
                  <td colspan="7" class="px-3 py-2">
                    <div class="h-4 w-44 animate-pulse rounded bg-muted"></div>
                  </td>
                </tr>
                <tr v-for="row in 10" :key="row" class="border-b border-border last:border-b-0">
                  <td v-for="col in 7" :key="col" class="px-3 py-2.5">
                    <div class="h-3.5 animate-pulse rounded bg-muted" :class="col === 1 ? 'w-40' : 'w-16'"></div>
                  </td>
                </tr>
              </tbody>
              <tbody v-else>
                <template v-for="row in displayRows" :key="row.key">
                  <tr
                    v-if="row.kind === 'header'"
                    class="border-b border-border"
                    :class="row.level === 0 ? 'border-t bg-muted' : 'bg-muted/10'"
                    data-testid="group-header"
                    :data-level="row.level"
                  >
                    <td colspan="7" class="px-3" :class="row.level === 0 ? 'py-2.5' : 'py-1.5 pl-8'">
                      <button
                        type="button"
                        class="flex w-full items-center justify-between gap-2 text-left"
                        :class="row.level === 0 ? 'text-base font-semibold' : 'text-sm font-medium'"
                        :aria-expanded="!collapsed.has(row.key)"
                        @click="toggleGroup(row.key)"
                      >
                        <span class="flex items-center gap-2">
                          <span
                            v-if="row.color"
                            class="inline-block size-2.5 rounded-full"
                            :style="{ backgroundColor: row.color }"
                            aria-hidden="true"
                          ></span>
                          {{ row.label }}
                        </span>
                        <ChevronDown
                          class="size-4 text-muted-foreground transition-transform"
                          :class="collapsed.has(row.key) ? '-rotate-90' : ''"
                          aria-hidden="true"
                        />
                      </button>
                    </td>
                  </tr>
                  <tr
                    v-else
                    class="cursor-pointer border-b border-border transition-colors last:border-b-0 hover:bg-accent"
                  >
                    <td class="px-3 py-2">
                      <a :href="`/alerts/${row.alert.chain}/`" class="flex items-center gap-2 font-medium">
                        <span
                          class="inline-block size-2.5 shrink-0 rounded-full"
                          :style="{ backgroundColor: severityColor(row.alert.severity) }"
                          aria-hidden="true"
                        ></span>
                        <span class="max-w-64 truncate">{{ row.alert.headline || row.alert.event }}</span>
                      </a>
                    </td>
                    <td class="px-3 py-2">{{ row.alert.severity }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ row.alert.authority_name }}</td>
                    <td class="px-3 py-2 uppercase text-muted-foreground">{{ row.alert.countries.join(", ") }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ fmt(row.alert.effective) }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ fmt(row.alert.expires) }}</td>
                    <td class="px-3 py-2 text-muted-foreground">{{ row.alert.status }}{{ row.alert.is_cancelled ? " (cancelled)" : "" }}</td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>

          <div v-if="state === 'ready' && total > TABLE_PAGE_SIZE" class="flex items-center justify-between text-sm text-muted-foreground">
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
