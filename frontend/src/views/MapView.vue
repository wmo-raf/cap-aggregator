<script setup lang="ts">
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import BasemapSwitcher from "@/components/BasemapSwitcher.vue";
import SeverityLegend from "@/components/SeverityLegend.vue";
import { useTheme } from "@/composables/useTheme";
import { ALERTS_SOURCE_ID, alertLayers } from "@/lib/alertLayers";
import { type BasemapId, basemapStyleUrl, resolveBasemapId } from "@/lib/basemap";
import { alertTileUrlTemplate } from "@/lib/config";

const container = ref<HTMLDivElement | null>(null);
let map: maplibregl.Map | null = null;

const { isDark } = useTheme();
// null until the user picks explicitly; before that the basemap follows the theme
const manualBasemap = ref<BasemapId | null>(null);
const activeBasemap = computed(() => resolveBasemapId(manualBasemap.value, isDark.value));

// setStyle wipes custom sources/layers, so this runs on every style.load
function addAlertLayers(target: maplibregl.Map) {
  if (!target.getSource(ALERTS_SOURCE_ID)) {
    target.addSource(ALERTS_SOURCE_ID, {
      type: "vector",
      tiles: [alertTileUrlTemplate()],
      minzoom: 0,
      maxzoom: 14,
    });
  }
  for (const layer of alertLayers()) {
    if (!target.getLayer(layer.id)) target.addLayer(layer);
  }
}

watch(activeBasemap, (id) => {
  map?.setStyle(basemapStyleUrl(id));
});

onMounted(() => {
  if (!container.value) return;
  map = new maplibregl.Map({
    container: container.value,
    style: basemapStyleUrl(activeBasemap.value),
    center: [15, 10],
    zoom: 2,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.on("style.load", () => addAlertLayers(map!));
});

onUnmounted(() => {
  map?.remove();
  map = null;
});
</script>

<template>
  <div class="relative h-full w-full">
    <!-- maplibre's own .maplibregl-map class forces position:relative, so size explicitly rather than with absolute/inset -->
    <div ref="container" class="h-full w-full" data-testid="map-container"></div>
    <div class="pointer-events-none absolute inset-0 z-10">
      <div class="absolute bottom-6 left-3">
        <SeverityLegend />
      </div>
      <div class="absolute right-3 bottom-6">
        <BasemapSwitcher :active="activeBasemap" @select="manualBasemap = $event" />
      </div>
    </div>
  </div>
</template>
