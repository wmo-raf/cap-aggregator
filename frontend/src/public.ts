import "@/assets/main.css";

// Server-rendered public pages (base.html): design tokens + the header theme
// toggle. The theme itself is applied pre-paint by includes/theme_boot.html.
const STORAGE_KEY = "capagg-theme";

function syncLabels() {
  const dark = document.documentElement.classList.contains("dark");
  document.querySelectorAll("[data-theme-label]").forEach((el) => {
    el.textContent = dark ? "Light" : "Dark";
  });
}

document.addEventListener("DOMContentLoaded", () => {
  syncLabels();
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const dark = document.documentElement.classList.toggle("dark");
      localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
      syncLabels();
    });
  });

  // Homepage alert groups: all alerts are in the HTML. One state function
  // drives visibility from (severity filter, per-group expansion):
  //  - no filter: first two per group, "View N more" expands the rest
  //  - filter active: ALL matching alerts show (collapse suspended, expand
  //    buttons hidden), empty groups disappear, header counts reflect matches
  const filterBoxes = [...document.querySelectorAll<HTMLInputElement>("[data-severity-filter]")];
  const groups = [...document.querySelectorAll<HTMLElement>("[data-alert-group]")];

  function applyAlertVisibility() {
    const selected = filterBoxes.filter((box) => box.checked).map((box) => box.value);
    const filtering = selected.length > 0;

    for (const group of groups) {
      const button = group.querySelector<HTMLButtonElement>("[data-expand-alerts]");
      const expanded = button?.getAttribute("aria-expanded") === "true";
      let visible = 0;

      group.querySelectorAll<HTMLElement>("li[data-severity]").forEach((item) => {
        const show = filtering
          ? selected.includes(item.dataset.severity ?? "")
          : !("extra" in item.dataset) || expanded;
        item.classList.toggle("hidden", !show);
        if (show) visible += 1;
      });

      if (button) button.classList.toggle("hidden", filtering);
      const count = group.querySelector("[data-group-count]");
      if (count) count.textContent = filtering ? String(visible) : (group.dataset.total ?? "");
      group.classList.toggle("hidden", filtering && visible === 0);
    }
  }

  document.querySelectorAll<HTMLButtonElement>("[data-expand-alerts]").forEach((button) => {
    button.addEventListener("click", () => {
      const expand = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(expand));
      button.textContent = expand ? "Show less" : (button.dataset.moreLabel ?? "View more");
      applyAlertVisibility();
    });
  });
  filterBoxes.forEach((box) => box.addEventListener("change", applyAlertVisibility));
});
