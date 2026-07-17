import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { ALERTS_SOURCE_ID, alertLayers } from "@/lib/alertLayers";
import { basemapStyleUrl, resolveBasemapId } from "@/lib/basemap";
import { alertTileUrlTemplate } from "@/lib/config";
import { activeAt, deriveTimeButtons, type TimeButton } from "@/lib/timeButtons";
import { buildPopupContent, dedupeAlertFeatures } from "@/lib/popup";
import { roundToBucket } from "@/lib/timeControl";

// Homepage active-alerts section: a browse-lite MapLibre map (pan + zoom
// buttons, no scroll hijack) and the per-authority alert list, both driven by
// one (severity, time) state. The list is the server-rendered union of active
// and upcoming alerts; items carry data-effective/data-expires and are
// toggled client-side for the selected instant.

const INITIAL_CENTER: [number, number] = [15, 10];
const INITIAL_ZOOM = 1.8;

document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("capagg-home-map");
  if (!container) return;

  const filterBoxes = [...document.querySelectorAll<HTMLInputElement>("[data-severity-filter]")];
  const groups = [...document.querySelectorAll<HTMLElement>("[data-alert-group]")];
  const timeControl = document.querySelector<HTMLElement>("[data-time-control]");
  const timeLabel = document.querySelector<HTMLElement>("[data-time-label]");

  let selectedTime: Date | null = null; // null = Now (live)

  const selectedSeverities = () => filterBoxes.filter((box) => box.checked).map((box) => box.value);

  // --- List visibility: one predicate over (time, severity, expansion) ---
  //  - Now + no severity: active items, first two per group, rest expandable
  //  - any filter or a future instant: ALL matching items show, expand
  //    buttons hidden; header counts track matches; empty groups disappear
  function applyAlertVisibility() {
    const severities = selectedSeverities();
    const t = selectedTime ?? new Date();
    const filtering = severities.length > 0 || selectedTime !== null;
    let anyMatch = false;

    for (const group of groups) {
      const button = group.querySelector<HTMLButtonElement>("[data-expand-alerts]");
      const expanded = button?.getAttribute("aria-expanded") === "true";
      let matches = 0;

      group.querySelectorAll<HTMLElement>("li[data-severity]").forEach((item) => {
        const alive = activeAt(
          { effective: item.dataset.effective || null, expires: item.dataset.expires || null },
          t,
        );
        const severityOk = !severities.length || severities.includes(item.dataset.severity ?? "");
        const match = alive && severityOk;
        if (match) matches += 1;
        const show = match && (filtering || !("extra" in item.dataset) || expanded);
        item.classList.toggle("hidden", !show);
      });

      if (button) button.classList.toggle("hidden", filtering);
      const count = group.querySelector("[data-group-count]");
      if (count) count.textContent = String(matches);
      group.classList.toggle("hidden", matches === 0);
      if (matches > 0) anyMatch = true;
    }

    document.querySelector("[data-alerts-empty]")?.classList.toggle("hidden", anyMatch);
  }

  document.querySelectorAll<HTMLButtonElement>("[data-expand-alerts]").forEach((button) => {
    button.addEventListener("click", () => {
      const expand = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(expand));
      button.textContent = expand ? "Show less" : (button.dataset.moreLabel ?? "View more");
      applyAlertVisibility();
    });
  });

  // --- Map (browse-lite) ---
  const isDark = () => document.documentElement.classList.contains("dark");

  function tileUrl(): string {
    const params = new URLSearchParams();
    // Public current situation: only Actual alerts are real warnings — keep in
    // sync with the homepage stats/list queries (HomePage.get_context)
    params.set("status", "Actual");
    const severities = selectedSeverities();
    // the tile function matches stored capitalized values ("Severe")
    if (severities.length) {
      params.set("severity", severities.map((s) => s[0].toUpperCase() + s.slice(1)).join(","));
    }
    if (selectedTime) params.set("t", roundToBucket(selectedTime).toISOString());
    return `${alertTileUrlTemplate()}?${params.toString()}`;
  }

  const map = new maplibregl.Map({
    container,
    style: basemapStyleUrl(resolveBasemapId(null, isDark())),
    center: INITIAL_CENTER,
    zoom: INITIAL_ZOOM,
    scrollZoom: false,
    attributionControl: false, // re-added top-right, clear of the time control
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "top-right");

  // setStyle wipes custom sources/layers, so this runs on every style.load
  map.on("style.load", () => {
    if (!map.getSource(ALERTS_SOURCE_ID)) {
      map.addSource(ALERTS_SOURCE_ID, { type: "vector", tiles: [tileUrl()], minzoom: 0, maxzoom: 14 });
    }
    for (const layer of alertLayers()) {
      if (!map.getLayer(layer.id)) map.addLayer(layer);
    }
  });

  // Follow the header theme toggle without a reload
  new MutationObserver(() => {
    map.setStyle(basemapStyleUrl(resolveBasemapId(null, isDark())));
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

  const clickableLayers = ["capagg-alerts-fill", "capagg-alerts-centroids"];
  map.on("click", (e) => {
    const layers = clickableLayers.filter((id) => map.getLayer(id));
    if (!layers.length) return;
    const alerts = dedupeAlertFeatures(map.queryRenderedFeatures(e.point, { layers }));
    if (!alerts.length) return;
    new maplibregl.Popup({ maxWidth: "320px" })
      .setLngLat(e.lngLat)
      .setDOMContent(buildPopupContent(alerts))
      .addTo(map);
  });
  for (const layerId of clickableLayers) {
    map.on("mouseenter", layerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", layerId, () => {
      map.getCanvas().style.cursor = "";
    });
  }

  function refreshTiles() {
    const source = map.getSource(ALERTS_SOURCE_ID) as maplibregl.VectorTileSource | undefined;
    source?.setTiles([tileUrl()]);
  }

  // --- Time selector: buttons derived from the list's time windows ---
  const instantLabel = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

  function selectTime(button: TimeButton) {
    selectedTime = button.t;
    timeControl?.querySelectorAll("[data-time-button]").forEach((el) => {
      el.setAttribute("aria-pressed", String(el.getAttribute("data-time-button") === button.key));
    });
    if (timeLabel) timeLabel.textContent = button.t ? `· at ${instantLabel.format(button.t)}` : "";
    refreshTiles();
    applyAlertVisibility();
  }

  if (timeControl) {
    const windows = groups
      .flatMap((group) => [...group.querySelectorAll<HTMLElement>("li[data-severity]")])
      .map((item) => ({ effective: item.dataset.effective || null, expires: item.dataset.expires || null }));
    for (const button of deriveTimeButtons(windows, new Date())) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "capagg-time-chip";
      el.textContent = button.label;
      el.setAttribute("data-time-button", button.key);
      el.setAttribute("aria-pressed", String(button.key === "now"));
      el.addEventListener("click", () => selectTime(button));
      timeControl.append(el);
    }
  }

  filterBoxes.forEach((box) =>
    box.addEventListener("change", () => {
      refreshTiles();
      applyAlertVisibility();
    }),
  );

  applyAlertVisibility(); // hide anything that expired since the server render
});
