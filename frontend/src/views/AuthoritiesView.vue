<script setup lang="ts">
import { ExternalLink } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import ExplorerSidebar from "@/components/ExplorerSidebar.vue";
import { type Authority, fetchAuthorities } from "@/lib/api";
import {
  type AuthoritiesState,
  groupByCountry,
  stateFromQuery,
  stateToQuery,
} from "@/lib/authoritiesState";
import { countryFlagEmoji } from "@/lib/countryFlag";

const route = useRoute();
const router = useRouter();

const authorities = ref<Authority[]>([]);
const loadState = ref<"loading" | "ready" | "error">("loading");
const sidebar = ref<AuthoritiesState>(stateFromQuery(route.query as Record<string, unknown>));

watch(sidebar, () => {
  const query = { ...route.query };
  delete query.active;
  delete query.group;
  router.replace({ query: { ...query, ...stateToQuery(sidebar.value) } });
}, { deep: true });

const visible = computed(() =>
  sidebar.value.activeOnly ? authorities.value.filter((a) => a.active_alert_count > 0) : authorities.value,
);
const countryGroups = computed(() => groupByCountry(visible.value));

onMounted(async () => {
  try {
    authorities.value = await fetchAuthorities();
    loadState.value = "ready";
  } catch {
    loadState.value = "error";
  }
});
</script>

<template>
  <section class="relative flex h-full w-full">
    <ExplorerSidebar title="Alerting authorities" description="National authorities whose CAP alerts this aggregator carries.">
        <section class="sidebar-panel" aria-label="Authority filters">
          <header class="sidebar-panel__header">
            <h3>Filters</h3>
          </header>
          <div class="flex flex-col gap-3 p-3">
            <label class="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
              <input
                type="checkbox"
                class="size-3.5 accent-primary"
                :checked="sidebar.activeOnly"
                data-testid="active-only"
                @change="sidebar = { ...sidebar, activeOnly: !sidebar.activeOnly }"
              />
              With active alerts
            </label>

            <fieldset class="flex flex-col gap-1">
              <legend class="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Group</legend>
              <label class="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
                <input type="radio" name="authority-group" class="size-3.5 accent-primary" :checked="sidebar.group === 'flat'" @change="sidebar = { ...sidebar, group: 'flat' }" />
                Flat list
              </label>
              <label class="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
                <input type="radio" name="authority-group" class="size-3.5 accent-primary" :checked="sidebar.group === 'country'" @change="sidebar = { ...sidebar, group: 'country' }" />
                By country
              </label>
            </fieldset>
          </div>
        </section>
      </ExplorerSidebar>

      <div class="min-w-0 flex-1 overflow-auto p-4 md:p-6">
        <p v-if="loadState === 'loading'" class="text-sm text-muted-foreground">Loading authorities…</p>
        <p v-else-if="loadState === 'error'" class="text-sm text-destructive" role="alert">
          Could not load the authorities list. Please try again later.
        </p>
        <p v-else-if="!visible.length" class="text-sm text-muted-foreground">
          No authorities match the current filters.
        </p>

        <ul v-else-if="sidebar.group === 'flat'" class="flex flex-col gap-3">
          <li v-for="authority in visible" :key="authority.slug">
            <article class="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4">
              <div class="flex min-w-0 items-center gap-3">
                <span class="text-2xl" aria-hidden="true">{{ countryFlagEmoji(authority.country) }}</span>
                <div class="min-w-0">
                  <p class="truncate font-medium">{{ authority.name }}</p>
                  <p class="text-sm text-muted-foreground">{{ authority.country_name }}</p>
                </div>
              </div>
              <div class="flex shrink-0 items-center gap-4">
                <span
                  data-testid="alert-count"
                  class="rounded-full border border-border bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground"
                  :title="`${authority.active_alert_count} currently active alert(s)`"
                >
                  {{ authority.active_alert_count }} active
                </span>
                <a
                  v-if="authority.website"
                  :href="authority.website"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  Website
                  <ExternalLink class="size-3.5" aria-hidden="true" />
                </a>
              </div>
            </article>
          </li>
        </ul>

        <div v-else class="flex flex-col gap-5">
          <section v-for="group in countryGroups" :key="group.code" :aria-label="group.name">
            <h2 class="mb-2 flex items-center gap-2 text-sm font-semibold" :data-country-group="group.code">
              <span aria-hidden="true">{{ countryFlagEmoji(group.code) }}</span>
              {{ group.name }}
              <span class="text-xs font-normal text-muted-foreground">{{ group.items.length }}</span>
            </h2>
            <ul class="flex flex-col gap-3">
              <li v-for="authority in group.items" :key="authority.slug">
                <article class="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4">
                  <p class="min-w-0 truncate font-medium">{{ authority.name }}</p>
                  <div class="flex shrink-0 items-center gap-4">
                    <span class="rounded-full border border-border bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
                      {{ authority.active_alert_count }} active
                    </span>
                    <a
                      v-if="authority.website"
                      :href="authority.website"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      Website
                      <ExternalLink class="size-3.5" aria-hidden="true" />
                    </a>
                  </div>
                </article>
              </li>
            </ul>
          </section>
        </div>
      </div>
  </section>
</template>
