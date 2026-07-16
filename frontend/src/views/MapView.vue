<script setup lang="ts">
import { RotateCcw } from "lucide-vue-next";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import AlertSidebar from "@/components/AlertSidebar.vue";
import BasemapSwitcher from "@/components/BasemapSwitcher.vue";
import SeverityLegend from "@/components/SeverityLegend.vue";
import TimeControl from "@/components/TimeControl.vue";
import { SIDEBAR_TRANSITION_MS, useSidebar } from "@/composables/useSidebar";
import { useTheme } from "@/composables/useTheme";
import { ALERTS_SOURCE_ID, alertLayers } from "@/lib/alertLayers";
import { type AlertListItem, fetchAlertList, fetchAlertWindows, fetchAuthorities } from "@/lib/api";
import { type BasemapId, basemapStyleUrl, resolveBasemapId } from "@/lib/basemap";
import { alertTileUrlTemplate } from "@/lib/config";
import {
  type AlertFilters,
  emptyFilters,
  FACET_PARAMS,
  filtersFromRouteQuery,
  filtersToRouteQuery,
  tileQueryFromFilters,
} from "@/lib/filters";
import { buildPopupContent, dedupeAlertFeatures } from "@/lib/popup";
import { roundToBucket, timeFromQuery, timeToQuery } from "@/lib/timeControl";

const INITIAL_CENTER: [number, number] = [15, 10];
const INITIAL_ZOOM = 2;

const container = ref<HTMLDivElement | null>(null);
let map: maplibregl.Map | null = null;

const route = useRoute();
const router = useRouter();
const { isDark } = useTheme();

// Resize the canvas once after the sidebar push settles (and on real window
// resizes) instead of MapLibre's trackResize: its ResizeObserver fires every
// animation frame, and the per-frame canvas reallocations flicker.
const sidebarOpen = useSidebar().isOpen("map");
let settleTimer: ReturnType<typeof setTimeout> | undefined;
watch(sidebarOpen, () => {
  clearTimeout(settleTimer);
  settleTimer = setTimeout(() => map?.resize(), SIDEBAR_TRANSITION_MS + 50);
});
const onWindowResize = () => map?.resize();

// null until the user picks explicitly; before that the basemap follows the theme
const manualBasemap = ref<BasemapId | null>(null);
const activeBasemap = computed(() => resolveBasemapId(manualBasemap.value, isDark.value));

// --- Filters + selected time: URL is the source of truth (deep-linkable) ---
const filters = ref<AlertFilters>(filtersFromRouteQuery(route.query));
const selectedTime = ref<Date | null>(timeFromQuery(route.query));

// Active + upcoming alert windows (global) — the time control's Live chips
const timeWindows = ref<{ effective: string | null; expires: string | null }[]>([]);

function tileUrl(): string {
  const params = new URLSearchParams(tileQueryFromFilters(filters.value));
  if (selectedTime.value) params.set("t", roundToBucket(selectedTime.value).toISOString());
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

// Global active-alert count for the fixed card — ignores filters/viewport/time
const globalCount = ref<number | null>(null);

async function refreshGlobalCount() {
  try {
    globalCount.value = (await fetchAlertList(emptyFilters(), null)).total;
  } catch {
    globalCount.value = null;
  }
}

/** One-click "show me everything, fresh": clear facets, back to live, home view. */
function resetAll() {
  filters.value = emptyFilters();
  selectedTime.value = null;
  map?.flyTo({ center: INITIAL_CENTER, zoom: INITIAL_ZOOM });
  refreshGlobalCount();
}

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
        const page = await fetchAlertList(filters.value, currentBbox(), selectedTime.value);
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

function syncState() {
  // sync URL: facets + time, preserving anything else
  const query = { ...route.query };
  for (const param of [...FACET_PARAMS, "t"]) delete query[param];
  router.replace({ query: { ...query, ...filtersToRouteQuery(filters.value), ...timeToQuery(selectedTime.value) } });
  // sync tiles + list
  const source = map?.getSource(ALERTS_SOURCE_ID) as maplibregl.VectorTileSource | undefined;
  source?.setTiles([tileUrl()]);
  refreshList(true);
}

watch(filters, syncState, { deep: true });
watch(selectedTime, syncState);

watch(activeBasemap, (id) => {
  map?.setStyle(basemapStyleUrl(id));
});

onMounted(async () => {
  if (!container.value) return;
  map = new maplibregl.Map({
    container: container.value,
    style: basemapStyleUrl(activeBasemap.value),
    center: INITIAL_CENTER,
    zoom: INITIAL_ZOOM,
    trackResize: false, // we settle once after the sidebar push instead
  });
  window.addEventListener("resize", onWindowResize);
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.on("style.load", () => addAlertLayers(map!));
  map.on("moveend", () => refreshList());

  // Click popups: every overlapping alert at the point, worst first.
  // Popups close on the next map click (maplibre closeOnClick default).
  const clickableLayers = ["capagg-alerts-fill", "capagg-alerts-centroids"];
  map.on("click", (e) => {
    const layers = clickableLayers.filter((id) => map!.getLayer(id));
    if (!layers.length) return;
    const alerts = dedupeAlertFeatures(map!.queryRenderedFeatures(e.point, { layers }));
    if (!alerts.length) return;
    new maplibregl.Popup({ maxWidth: "320px" })
      .setLngLat(e.lngLat)
      .setDOMContent(buildPopupContent(alerts))
      .addTo(map!);
  });
  for (const layerId of clickableLayers) {
    map.on("mouseenter", layerId, () => {
      map!.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", layerId, () => {
      map!.getCanvas().style.cursor = "";
    });
  }

  refreshList(true);
  refreshGlobalCount();

  try {
    timeWindows.value = await fetchAlertWindows();
  } catch {
    timeWindows.value = []; // chips degrade to just "Now"
  }

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
  clearTimeout(settleTimer);
  window.removeEventListener("resize", onWindowResize);
  map?.remove();
  map = null;
});
</script>

<template>
  <div class="relative flex h-full w-full">
    <AlertSidebar
      :alerts="alerts"
      :total="total"
      :state="listState"
      :filters="filters"
      :countries="countries"
      @update:filters="filters = $event"
    />
    <div class="relative min-w-0 flex-1">
      <!-- maplibre's own .maplibregl-map class forces position:relative, so size explicitly rather than with absolute/inset -->
      <div ref="container" class="h-full w-full" data-testid="map-container"></div>
      <div class="pointer-events-none absolute inset-0 z-10">
        <div class="pointer-events-auto absolute top-24 right-3 flex flex-col items-stretch gap-1.5 rounded-lg border border-border bg-card/95 px-3 py-2 shadow-sm backdrop-blur">
        <p class="text-center">
          <span class="block text-xl leading-tight font-semibold" data-testid="global-count">{{ globalCount ?? "—" }}</span>
          <span class="block text-[10px] tracking-wide text-muted-foreground uppercase">active alerts</span>
        </p>
        <button
          type="button"
          class="flex items-center justify-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          title="Clear filters, return to live, reset the view"
          data-testid="map-reset"
          @click="resetAll"
        >
          <RotateCcw class="size-3.5" aria-hidden="true" />
          Reset
        </button>
      </div>
        <div class="absolute right-3 bottom-6 flex flex-col items-end gap-2">
          <SeverityLegend />
          <BasemapSwitcher :active="activeBasemap" @select="manualBasemap = $event" />
        </div>
        <div class="absolute bottom-6 left-1/2 w-max min-w-[min(26rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] -translate-x-1/2">
          <TimeControl :model-value="selectedTime" :windows="timeWindows" @update:model-value="selectedTime = $event" />
        </div>
      </div>
    </div>
  </div>
</template>
