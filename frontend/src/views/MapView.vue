<script setup lang="ts">
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import AlertSidebar from "@/components/AlertSidebar.vue";
import BasemapSwitcher from "@/components/BasemapSwitcher.vue";
import SeverityLegend from "@/components/SeverityLegend.vue";
import { useTheme } from "@/composables/useTheme";
import { ALERTS_SOURCE_ID, alertLayers } from "@/lib/alertLayers";
import { type AlertListItem, fetchAlertList, fetchAuthorities } from "@/lib/api";
import { type BasemapId, basemapStyleUrl, resolveBasemapId } from "@/lib/basemap";
import { alertTileUrlTemplate } from "@/lib/config";
import {
  type AlertFilters,
  FACET_PARAMS,
  filtersFromRouteQuery,
  filtersToRouteQuery,
  tileQueryFromFilters,
} from "@/lib/filters";

const container = ref<HTMLDivElement | null>(null);
let map: maplibregl.Map | null = null;

const route = useRoute();
const router = useRouter();
const { isDark } = useTheme();

// null until the user picks explicitly; before that the basemap follows the theme
const manualBasemap = ref<BasemapId | null>(null);
const activeBasemap = computed(() => resolveBasemapId(manualBasemap.value, isDark.value));

// --- Filters: URL is the source of truth (deep-linkable) ---
const filters = ref<AlertFilters>(filtersFromRouteQuery(route.query));

function tileUrl(): string {
  const params = new URLSearchParams(tileQueryFromFilters(filters.value));
  const qs = params.toString();
  return qs ? `${alertTileUrlTemplate()}?${qs}` : alertTileUrlTemplate();
}

// setStyle wipes custom sources/layers, so this runs on every style.load
function addAlertLayers(target: maplibregl.Map) {
  if (!target.getSource(ALERTS_SOURCE_ID)) {
    target.addSource(ALERTS_SOURCE_ID, {
      type: "vector",
      tiles: [tileUrl()],
      minzoom: 0,
      maxzoom: 14,
    });
  }
  for (const layer of alertLayers()) {
    if (!target.getLayer(layer.id)) target.addLayer(layer);
  }
}

// --- Sidebar list: alerts within the current viewport ---
const alerts = ref<AlertListItem[]>([]);
const total = ref(0);
const listState = ref<"loading" | "ready" | "error">("loading");
const countries = ref<{ code: string; name: string }[]>([]);

let refreshTimer: ReturnType<typeof setTimeout> | undefined;

function currentBbox(): [number, number, number, number] | null {
  if (!map) return null;
  const b = map.getBounds();
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
}

function refreshList(immediate = false) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(
    async () => {
      listState.value = "loading";
      try {
        const page = await fetchAlertList(filters.value, currentBbox());
        alerts.value = page.alerts;
        total.value = page.total;
        listState.value = "ready";
      } catch {
        listState.value = "error";
      }
    },
    immediate ? 0 : 300,
  );
}

watch(
  filters,
  () => {
    // sync URL (preserving non-facet params like the future time param)
    const query = { ...route.query };
    for (const param of FACET_PARAMS) delete query[param];
    router.replace({ query: { ...query, ...filtersToRouteQuery(filters.value) } });
    // sync tiles + list
    const source = map?.getSource(ALERTS_SOURCE_ID) as maplibregl.VectorTileSource | undefined;
    source?.setTiles([tileUrl()]);
    refreshList(true);
  },
  { deep: true },
);

watch(activeBasemap, (id) => {
  map?.setStyle(basemapStyleUrl(id));
});

onMounted(async () => {
  if (!container.value) return;
  map = new maplibregl.Map({
    container: container.value,
    style: basemapStyleUrl(activeBasemap.value),
    center: [15, 10],
    zoom: 2,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.on("style.load", () => addAlertLayers(map!));
  map.on("moveend", () => refreshList());
  refreshList(true);

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

onUnmounted(() => {
  clearTimeout(refreshTimer);
  map?.remove();
  map = null;
});
</script>

<template>
  <div class="relative h-full w-full">
    <!-- maplibre's own .maplibregl-map class forces position:relative, so size explicitly rather than with absolute/inset -->
    <div ref="container" class="h-full w-full" data-testid="map-container"></div>
    <div class="pointer-events-none absolute inset-0 z-10">
      <div class="absolute top-0 bottom-0 left-0">
        <AlertSidebar
          :alerts="alerts"
          :total="total"
          :state="listState"
          :filters="filters"
          :countries="countries"
          @update:filters="filters = $event"
        />
      </div>
      <div class="absolute right-3 bottom-6 flex flex-col items-end gap-2">
        <SeverityLegend />
        <BasemapSwitcher :active="activeBasemap" @select="manualBasemap = $event" />
      </div>
    </div>
  </div>
</template>
